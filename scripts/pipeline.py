# -*- coding: utf-8 -*-
"""pipeline.py —— LangGraph 风格的编排流

把「规格 → HTML → 实测 → 校验 → 修正」编排成一张状态图，
节点是函数，边是条件跳转，状态是一个 dict。不依赖 langgraph 包
（结构同构：State / Node / Conditional Edge，需要时可以一行换成真 LangGraph）。

    ┌─────────┐    ┌─────────┐    ┌────────┐
    │  build  │ →  │ measure │ →  │ verify │
    └─────────┘    └─────────┘    └───┬──────┘
         ↑                           │
         │            ┌──────────────┴──────┐
         └──── 修正 ← │ 溢出 ≤3 轮：校准/缩字│
                      │ 仍溢出：标记给 LLM  │
                      └─────────────────────┘

为什么二次校验必须用真实浏览器：ink.tw() 是估算，字体度量估不准
（拉丁宽、bold、letter-spacing 都是变量），估算器说没问题、图上照样出框。
measure 节点让 Chrome 渲染后用 getBBox() 拿**真实**包围盒，
再把「真实宽 / 估算宽」回写成校准因子——估算器自己越跑越准。

LLM 的位置（两层兜底）：
  1. 写规格时就把文案压到行宽内（事前）
  2. 循环 3 轮仍溢出的行，进入 needs_llm 清单——
     那是「该重写文案」的信号，由 Agent 改规格后再走一遍（事后）
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ink  # noqa: E402
from measure import measure_and_analyze  # noqa: E402
from render import find_browser, shoot, file_url  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_ITER = 3

# ★ 软提示类问题：**不挡交付**，只报给 agent 看。判定依据是 SKILL.md 的口径
#   （"dom-orphan 是提示，能改就改"；"真正会把 LLM 拉回来只有两类：
#   dom-overflow 和页数超硬上限"）。
#   早先 dom-orphan 和 dom-overflow 同桶 → 被写进 needs_llm、run.py 判成硬问题、
#   整轮 exit=1，agent 只能返工。实测为此白跑 2 轮（8 页稿，两条末行只剩 11% / 18% 宽）。
SOFT_KINDS = ("dom-orphan",)


# ---------------------------------------------------------------- 节点
def _targets(state):
    """这一轮要处理的卡号（1 起）。`only` 有值时只做那一张 —— 单页返工用。"""
    only = state.get("only")
    if only:
        return [only]
    return list(range(1, len(state["cards"]) + 1))


def node_build(state):
    """规格 → HTML（calib 会随迭代更新，tw() 越跑越准）。"""
    meta = dict(state["meta"])
    meta["calib"] = state["calib"]
    ink.CALIB[0] = state["calib"]
    outdir = state["build_dir"]
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    elif not state.get("only"):
        # 清掉上一次的卡片：规格从 9 页缩到 8 页时，残留的 card-09.html
        # 会被 render 当成第 9 张一起渲染出去（实测踩过）
        for f in os.listdir(outdir):
            if f.startswith("card-") and f.endswith(".html"):
                os.remove(os.path.join(outdir, f))
    # ★ --only 时**不清空**：其它页的 HTML 必须留着 —— 否则返工一页会顺手删掉
    #   整本的中间产物，再想返工第二页就得把全部重建一遍。
    # ★ ink.WARN 逐卡归因：这个列表是模块级的，只有 build.py 会打印它，
    # 走 pipeline 正常流程时**从来没输出过** —— 于是"缩字 / 截断 / 密集档"全是静默的
    # （实测被外部测试抓到：hub 的 en 被从 33px 压到 21px，流程里一声不响）。
    # 这里按卡切片，攒成本轮的降级报告。
    ink.WARN[:] = []
    degraded = {}
    for n in _targets(state):
        i = n - 1
        card = state["cards"][i]
        n0 = len(ink.WARN)
        html = ink.render_card(card, i, len(state["cards"]), meta, state["font_url"])
        with io.open(os.path.join(outdir, "card-%02d.html" % (i + 1)), "w",
                     encoding="utf-8") as f:
            f.write(html)
        new = ink.WARN[n0:]
        if new:
            degraded["card-%02d(%s)" % (i + 1, card.get("layout"))] = list(new)
    state["degraded"] = degraded
    line = "build: %d 页（calib=%.2f）" % (len(_targets(state)), state["calib"])
    if state.get("only"):
        line = "build: 只重建 card-%02d（calib=%.2f）" % (state["only"], state["calib"])
    if degraded:
        n = sum(len(v) for v in degraded.values())
        line += "  ⚠降级 %d 处（%d 页）" % (n, len(degraded))
    state["log"].append(line)


def node_measure(state):
    """逐页真实测量，收集溢出。"""
    issues = {}
    for n in _targets(state):
        hp = os.path.join(state["build_dir"], "card-%02d.html" % n)
        rep, iss = measure_and_analyze(hp, state["browser"])
        if iss:
            issues["card-%02d" % n] = iss
    state["issues"] = issues
    hard = sum(1 for v in issues.values() for i in v if i["kind"] not in SOFT_KINDS)
    soft = sum(1 for v in issues.values() for i in v if i["kind"] in SOFT_KINDS)
    # ★ 「N 处溢出」必须把孤字摘出去：dom-orphan 是**提示**（SKILL.md 明写"能改就改"），
    #   混进"溢出"的计数里会让 agent 以为必须返工（实测为此白跑 2 轮）。
    state["log"].append("measure: %d 处溢出%s"
                        % (hard, "（另有 %d 处孤字提示，不影响交付）" % soft if soft else ""))


def node_verify(state):
    """条件边：干净 → render；有溢出 → 分流。"""
    width_issues = {}
    layout_issues = []
    soft_issues = []
    for page, lst in state["issues"].items():
        for i in lst:
            if i["kind"] in SOFT_KINDS:
                # ★ 孤字 = "末行只剩 1~2 字"，SKILL.md 定性为**提示**，不该挡交付。
                #   单独一桶，既不进 needs_llm 也不进 autofix。
                soft_issues.append((page, i))
            elif (i["kind"] == "out-of-canvas" and i.get("where") == "y") \
                    or i["kind"] in ("v-overflow", "missing-text", "overlap",
                                     "crosses-line", "crosses-frame", "crosses-box",
                                     "dom-overflow"):
                # 版式 / 内容问题，脚本修不了：v-overflow 要减条数或拆页，
                # missing-text 是引擎把字吞了，几何门那几类（重叠/压线/压框/穿框）
                # 只能靠改文案或换版式 —— **绝不能喂给 autofix**：它不是宽度问题，
                # 注入 textLength 只会把字压扁，还会把 calib 抬高去污染无关卡片。
                # dom-overflow 同理：DOM 模式下浏览器已经把字号缩到最小，
                # 再注入 textLength 毫无意义（实测白烧 3 轮）→ 直接交回改文案或换版式。
                layout_issues.append((page, i))
            else:
                width_issues.setdefault(page, []).append(i)
    state["width_issues"] = width_issues
    state["layout_issues"] = layout_issues
    state["soft_issues"] = soft_issues


def node_autofix(state):
    """确定性修正：校准因子放大 + 对溢出的 SVG 文本注入 textLength。"""
    if not state["width_issues"]:
        # ★ 只有内容/版式问题（missing-text / v-overflow）时，脚本没有任何可做的：
        # 放大 calib 只会让 wrap_text 折得更早、截断更多，下一轮报得更多
        # （实测踩过：内容门报 1 处 → calib 1.18 → 报 2 处 → calib 1.39 → 报 3 处）。
        # 这类问题的唯一解是让人/Agent 改文案，所以直接返回，别污染宽度估算器。
        state["log"].append("autofix: 只有内容/版式问题，脚本无法修正，跳过校准")
        return
    state["calib"] = round(min(state["calib"] * 1.18, 2.0), 3)
    # 对仍溢出的文本直接注入 textLength（压回它所在的框/画布内）
    fixed = 0
    for page, lst in state["width_issues"].items():
        hp = os.path.join(state["build_dir"], page + ".html")
        src = io.open(hp, encoding="utf-8").read()
        tags = list(re.finditer(r"<text[^>]*>", src))
        for i in lst:
            idx = i.get("idx")
            if idx is None or idx >= len(tags) or "textLength" in tags[idx].group(0):
                continue
            target = (i.get("box_w") or ink.W_INNER) - 16
            if i["kind"] == "out-of-canvas":
                target = ink.W_INNER - 20
            m = tags[idx]
            tag = m.group(0)[:-1] + (" textLength='%.1f' "
                                     "lengthAdjust='spacingAndGlyphs'>" % target)
            src = src[:m.start()] + tag + src[m.end():]
            tags = list(re.finditer(r"<text[^>]*>", src))
            fixed += 1
        io.open(hp, "w", encoding="utf-8").write(src)
    state["log"].append("autofix: textLength 注入 %d 处" % fixed)


def node_render(state):
    browser = state["browser"]
    if not os.path.isdir(state["out_dir"]):
        os.makedirs(state["out_dir"])
    # ★ **不要预先删图**。原来先清空 card-*.png 再逐张渲染 —— 渲染中途失败会把
    #   上一次**本来是好的**成品一起删掉（实测：card-03 写不进去 → 01/02 也没了，
    #   于是"1 张失败"升级成"整套没了"，正好是用户最不想要的）。
    #   现在改成渲染成功后再清理"页数变少留下的旧图"，中途失败则旧图原样保留。
    # ★ --only 时不清空：返工一页不该动其它页。
    failed = []
    for n in _targets(state):
        hp = os.path.join(state["build_dir"], "card-%02d.html" % n)
        png = os.path.join(state["out_dir"], "card-%02d.png" % n)
        if not os.path.exists(hp):
            state["log"].append("render: card-%02d.html 不存在（先跑一次完整交付）" % n)
            failed.append("card-%02d" % n)
            continue
        try:
            ok, msg = shoot(browser, hp, png, 1080, 1440, 2)
            if not ok:
                # ★ 渲染是唯一要碰浏览器 + 文件系统的环节，最容易偶发失败
                #   （Chrome 冷启动慢、profile 被占、杀软正在扫刚写出的 PNG）。
                #   重试一次，别让一次抖动废掉一张图。
                time.sleep(1.0)
                ok, msg2 = shoot(browser, hp, png, 1080, 1440, 2)
                msg = (msg2 + "（重试 1 次后成功）") if ok else (msg + "｜重试仍失败：" + msg2)
        except Exception as e:                       # noqa: BLE001
            # ★ shoot() 也可能直接抛（权限、路径是目录、浏览器没了）。
            #   包住它：一张图出不来不该连带把整套都拖死。
            ok, msg = False, "渲染异常：%s" % e
        state["log"].append("render: %s %s"
                            % (os.path.basename(png),
                               # 浏览器原生报错动辄几百字符（含进程号/时间戳），
                               # 全打会把结论挤没；留前 160 字符够定位。
                               (msg[:160] + "…") if len(msg) > 160 else msg))
        if not ok:
            failed.append("card-%02d" % n)
    # 渲染成功（或至少没整体崩）之后，再清掉超出当前页数的残留旧图
    if not state.get("only") and os.path.isdir(state["out_dir"]):
        for f in os.listdir(state["out_dir"]):
            if not (f.startswith("card-") and f.endswith(".png")):
                continue
            try:
                idx = int(f[5:7])
            except ValueError:
                continue
            if idx > len(state["cards"]):
                os.remove(os.path.join(state["out_dir"], f))
    state["render_failed"] = failed


# ---------------------------------------------------------------- 图
def run(spec_path, out_dir, frame=None, no_decor=False, verbose=True, only=None):
    t0 = time.perf_counter()
    state = {
        "spec": spec_path, "meta": {}, "calib": 1.0, "issues": {}, "degraded": {},
        "log": [], "browser": find_browser(),
        "font_url": file_url(os.path.join(ROOT, "assets", "fonts",
                                          "ZCOOLKuaiLe-Regular.ttf")),
        "build_dir": os.path.join(ROOT, "build", os.path.splitext(
            os.path.basename(spec_path))[0]),
        "out_dir": os.path.abspath(out_dir),
        "only": only,
    }
    spec = _load(spec_path)
    state["cards"] = spec.get("cards") or []
    if only and not (1 <= only <= len(state["cards"])):
        raise SystemExit("--only %s 越界：这份规格只有 %d 页"
                         % (only, len(state["cards"])))
    meta = dict(spec.get("meta") or {})
    if frame:
        meta["frame"] = [frame]
    if no_decor:
        meta["decor"] = False
    state["meta"] = meta

    node_build(state)
    for it in range(1, MAX_ITER + 1):
        state["log"].append("--- 校验第 %d 轮 ---" % it)
        node_measure(state)
        node_verify(state)
        if not state["width_issues"] and not state["layout_issues"]:
            state["log"].append("verify: 干净，进入渲染")
            break
        if state["layout_issues"] and not state["width_issues"]:
            # 内容被吞 / 版式撑破：再跑几轮结果一模一样，直接点名给 LLM 改文案
            state["log"].append("verify: 内容或版式问题脚本修不了，直接交回 LLM 改文案")
            state["needs_llm"] = [(p, i.get("text", ""), i.get("note", ""))
                                  for p, i in state["layout_issues"]]
            break
        if it == MAX_ITER:
            state["log"].append("verify: %d 轮后仍有溢出，标记给 LLM 重写文案"
                                % MAX_ITER)
            state["needs_llm"] = [(p, i.get("text", ""), i.get("note", ""))
                                  for p, lst in state["width_issues"].items() for i in lst]
            state["needs_llm"] += [(p, i.get("text", ""), i.get("note", ""))
                                   for p, i in state["layout_issues"]]
            break
        node_autofix(state)
        node_build(state)
    node_render(state)

    if verbose:
        for line in state["log"]:
            print("  " + line)
        if state.get("degraded"):
            print("\n  ⚠ 降级报告（不是错误，但都是「为了放下字而做的妥协」，值得看一眼）：")
            for page, items in state["degraded"].items():
                for w in items:
                    print("    %s  %s" % (page, w))
        if state.get("needs_llm"):
            print("\n  ⚠ 以下文案需要 LLM 重写（脚本压不下了）：")
            for p, t, n in state["needs_llm"]:
                # ★ 一定要带 note（实测值）：只说"这条不行"、不说"差多少"，
                #   agent 就得靠试错猜要砍几个字，一轮变两三论。
                print("    %s  「%s」%s" % (p, t, ("  ← " + n) if n else ""))
        if state.get("soft_issues"):
            # ★ 单独一段、明写"不影响交付"：否则 agent 会把它当成必须改的硬问题，
            #   又白跑一轮（这正是 SOFT_KINDS 存在的原因）。
            print("\n  · 提示（**不影响交付**，能改更好）：")
            for p, i in state["soft_issues"]:
                print("    %s  「%s」%s"
                      % (p, i.get("text", ""), ("  ← " + i["note"]) if i.get("note") else ""))
        if state.get("render_failed"):
            # ★ 渲染失败原来只写进 log、退出码仍是 0 —— 于是"8 张里 1 张没出图"
            #   会被上游当成干净交付（实测踩过，用户看到的就是"有 1 张出问题了"）。
            print("\n  ✗ 以下页**没有出图**（渲染失败，重试过 1 次）：%s"
                  % " ".join(state["render_failed"]))
    state["seconds"] = time.perf_counter() - t0
    return state


def _load(path):
    text = io.open(path, encoding="utf-8").read()
    if path.lower().endswith(".json"):
        return json.loads(text)
    try:
        import yaml
    except ImportError:
        raise SystemExit("读 YAML 需要 pyyaml：pip install pyyaml（或用 .json 规格）")
    return yaml.safe_load(text)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LangGraph 风格编排流：规格 → 校验循环 → PNG")
    ap.add_argument("spec")
    ap.add_argument("-o", "--out", default="out")
    ap.add_argument("--frame", choices=["pen", "card", "none"])
    ap.add_argument("--no-decor", action="store_true")
    ap.add_argument("--only", type=int, metavar="N",
                    help="只重做第 N 页（1 起）：单页返工用，秒级出图、不动其它页")
    args = ap.parse_args()
    st = run(args.spec, args.out, frame=args.frame, no_decor=args.no_decor,
             only=args.only)
    print("\n耗时 %.1fs" % st["seconds"])
    # ★ 退出码必须反映"这份稿能不能交付"，不能只反映"我有没有崩"。
    #   原来只有渲染失败才非零；**有硬问题（needs_llm）时照样 exit=0** ——
    #   于是 `python scripts/pipeline.py ...` 单独跑一遍，明明报了
    #   "以下文案需要 LLM 重写"，退出码还是成功（tests/run.py 抓到的）。
    #   run.py 靠扫输出关键词兜住了，但那是巧合，不是契约。
    if st.get("render_failed"):
        print("✗ 渲染失败：%s（重试 1 次仍失败，可单独返工：--only N）"
              % " ".join(st["render_failed"]))
        sys.exit(1)
    if st.get("needs_llm"):
        print("✗ 有 %d 处文案放不下，必须改短（见上面的逐条与像素值）"
              % len(st["needs_llm"]))
        sys.exit(1)
    sys.exit(0)
