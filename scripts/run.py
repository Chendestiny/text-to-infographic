# -*- coding: utf-8 -*-
"""run.py —— 一条命令交付：过四道门 + 出图 + 生成复核缩略图 + 一份结论。

为什么要合成一条（用户实测的痛点）：一轮生图跑到 **19~31 次工具调用**、4 轮返工，
其中大量是"每条门各跑一次、再自己把几份输出拼起来判断"。这里全部合成一次调用。

    python scripts/run.py <spec.json> [--article <文章.md>] [--out <出图目录>]

它依次做：
    ① 文字级预检（孤字 / 断词 / 数量词）      零成本，不起浏览器
    ② 页数对账（给了文章才做：plan.py --check）
    ③ 规格门（结构 + 几何硬墙）
    ④ 像素门 + 几何布局门（起一次浏览器）
    ⑤ 复核缩略图（720px，看图时抽查 1~2 张就够）
最后给一句结论：可以交付 / 必须改什么。

退出码：0 = 可以交付；1 = 有硬问题
"""
import argparse
import io
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# ★ 每个阶段的超时预算（秒）。实测正常耗时：各门 <1s，pipeline 约 1s/页
#   （7 页 ≈ 7s）。这里留 30~80 倍余量 —— 目的是**卡住时能在可接受时间内报错退出**，
#   不是掐正常执行；调大不会变慢，只会让卡死更难被发现。
#   为什么必须有：run() 原来是裸的 subprocess.run，**没有任何 timeout**，
#   任何一道门挂住（浏览器不响应、CDP 卡在 recv）就是无限等待 ——
#   这正是用户实测"10 次至少 4 次卡壳"的结构性根源。
STAGE_TIMEOUT = {
    "plan.py": 90,
    "preflight.py": 60,
    "validate.py": 60,
    "capacity.py": 60,
    "pipeline.py": 600,
    "review_sheet.py": 120,
}
DEFAULT_TIMEOUT = 120


def _stage_timeout(script):
    """取某阶段的超时预算。`T2I_TIMEOUT_SCALE` 可整体缩放（慢机器上放宽、
    测试时收紧 —— 否则超时这条路径根本没法验证）。"""
    base = STAGE_TIMEOUT.get(script, DEFAULT_TIMEOUT)
    try:
        return max(1, int(base * float(os.environ.get("T2I_TIMEOUT_SCALE") or 1)))
    except ValueError:
        return base


def run(script, *args, **kw):
    env = dict(os.environ)
    env.setdefault("T2I_BACKEND", os.environ.get("T2I_BACKEND", "cdp"))
    t = kw.get("timeout") or _stage_timeout(script)
    cmd = [sys.executable, os.path.join(HERE, script)] + [str(a) for a in args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", cwd=ROOT, env=env, timeout=t)
    except subprocess.TimeoutExpired:
        return ("✗ %s 超时（%ds，已强制中止，不再无限等待）" % (script, t), 124)
    return (p.stdout or "") + (p.stderr or ""), p.returncode


def rework(spec, only, out, theme=None):
    """单页返工：只重建 / 重测 / 重出第 only 页，其它页的 HTML 与 PNG 原样不动。

    为什么需要（用户提的人在回路）：整套 8 张里只有 1 张不满意时，
    重跑全量既慢又可能把好的那 7 张也重出成别的样子；用户要的是
    "我说第 5 张不行，你就只改第 5 张"。实测一页 ≈ 1~2 秒。
    """
    print("单页返工：card-%02d（其它页不动）" % only)
    print("-" * 64)
    hard = []
    # 规格门照跑：它便宜（~0.2s），而且改文案最容易踩的就是它
    o, rc = run("validate.py", spec)
    line = ([l.strip() for l in o.splitlines()
             if "契约校验" in l or "契约违规" in l] or ["✗ 未跑完"])[0]
    print("  规格门   " + line)
    if "契约校验" not in o and "契约违规" not in o:
        hard.append("规格门｜validate.py 未跑完（exit=%d）：%s"
                    % (rc, (o.strip().splitlines() or [""])[-1][:110]))

    extra = ["--theme", theme] if theme else []
    o, rc = run("pipeline.py", spec, "-o", out, "--only", only, *extra)
    for l in o.splitlines():
        s = l.strip()
        if s.startswith(("build:", "measure:", "verify:", "render:", "耗时", "✗")):
            print("  " + s)
        if s.startswith("✗"):
            hard.append("像素门｜" + s[:120])
    if rc != 0 and "measure:" not in o:
        hard.append("像素门｜pipeline 异常退出（exit=%d）" % rc)

    if not hard:
        o2, _ = run("review_sheet.py", out)      # 让拼版缩略图跟上新图
        for l in o2.splitlines():
            if "真要看观感时" in l:
                print("  复核图   " + l.strip()[:90])
    print("=" * 64)
    if hard:
        print("✗ card-%02d 返工未完成：" % only)
        for h in hard[:8]:
            print("   " + h)
        return 1
    print("✓ card-%02d 已重新出图，其余页未改动。" % only)
    print("  产物：%s" % os.path.join(out, "card-%02d.png" % only))
    return 0


def main():
    ap = argparse.ArgumentParser(description="一条命令交付")
    ap.add_argument("spec", nargs="?", help="规格文件；用 --plan 时可以省略")
    ap.add_argument("--plan", metavar="ARTICLE.md",
                    help="只做页数规划（内部就是 plan.py）：打印张数/区间/页骨架/可粘贴的 meta.plan")
    ap.add_argument("--article", help="给了就做页数对账")
    ap.add_argument("--out", help="出图目录（默认 spec 所在目录）")
    ap.add_argument("--budget", action="store_true",
                    help="顺带打印每槽字数预算表（写文案前用，省一次 capacity.py 调用）")
    ap.add_argument("--no-render", action="store_true", help="只过门不出图（写规格阶段用）")
    ap.add_argument("--only", type=int, metavar="N",
                    help="只重做第 N 页（1 起）：改完某页文案后用它，秒级出图、不动其它页")
    ap.add_argument("--theme", help="覆盖 meta.theme（皮肤 key，见 scripts/theme.py --list）")
    a = ap.parse_args()

    if a.plan:                      # 规划模式：一条命令入口收敛到 run.py
        o, _ = run("plan.py", a.plan)
        print(o.rstrip())
        return 0
    if not a.spec:
        print("用法：run.py <spec.json> [--article 文章.md] [--out 目录] [--theme 皮肤] "
              "| run.py --plan 文章.md")
        return 2
    spec = os.path.abspath(a.spec)
    out = a.out or os.path.dirname(spec)
    if a.only:
        return rework(spec, a.only, out, a.theme)
    hard, soft = [], []
    pipe_out = ""               # ★ --no-render 时不会跑 pipeline，先给它一个空值

    o, rc_pre = run("preflight.py", spec)
    for l in o.splitlines():
        if l.strip().startswith("✗"):
            hard.append("预检｜" + l.strip())
    # ★ 没打出结论行 = 脚本压根没跑完（缺依赖 / 抛异常），**不能当成"没问题"**。
    #   这就是假绿：门没跑，却报 exit=0。实测踩过 —— 受管 Python 没装 pyyaml，
    #   validate.py 直接 SystemExit，run.py 照样输出"✓ 硬问题 0 处"。
    if "文字级预检" not in o:
        hard.append("预检｜preflight.py 未跑完（exit=%d）：%s"
                    % (rc_pre, (o.strip().splitlines() or [""])[-1][:110]))
    print("① 预检     " + ([l.strip() for l in o.splitlines() if "文字级预检" in l]
                            or ["✗ 未跑完（见结论）"])[0])

    if a.article:
        o, _ = run("plan.py", a.article, "--check", spec)
        for l in o.splitlines():
            if "对账" in l:
                print("② 页数     " + l.strip())
            elif "超过硬上限" in l:
                hard.append("页数｜" + l.strip())
            elif "⚠" in l:
                soft.append(l.strip())

    o, rc = run("validate.py", spec)
    spec_out = o          # ★ 留一份：下面 o 会被 review_sheet 覆盖，
                          #   而交付报告要引用规格门的结论（原来就引错了输出）
    for l in o.splitlines():
        s = l.strip()
        if s.endswith("：") or re.match(r"^(页数提示|契约违规|软约束|密集档提示|超过建议字数)", s):
            continue
        if re.search(r"几何上放不下|未知字段|不渲染|条数越界|超过硬上限", s):
            hard.append("规格门｜" + s[:120])
    # ★ 同上：判定"跑没跑完"要看结论行。原来只找"契约校验"，而失败时打的是
    #   "契约违规" —— 于是**违规**和**崩溃**都落到同一个"（有提示，见下）"，
    #   崩溃就被吞成了软提示。
    if "契约校验" not in o and "契约违规" not in o:
        hard.append("规格门｜validate.py 未跑完（exit=%d）：%s"
                    % (rc, (o.strip().splitlines() or [""])[-1][:110]))
    print("③ 规格门   " + ([l.strip() for l in o.splitlines()
                            if "契约校验" in l or "契约违规" in l]
                            or ["✗ 未跑完（见结论）"])[0])

    if a.budget:
        ob, _ = run("capacity.py", spec, "--budget")
        for l in ob.splitlines():
            if "约 " in l or "预算表" in l:
                print("    " + l.strip())
    if a.no_render:
        print("④ 像素门   （--no-render：跳过出图与实测）")
        pipe_out = o = ""
    else:
        _extra = ["--theme", a.theme] if a.theme else []
        o, rc_pipe = run("pipeline.py", spec, "-o", out, *_extra)
        if rc_pipe != 0 and "measure:" not in o:
            # ★ 崩溃/超时**重试一次**：渲染要碰浏览器和文件系统，偶发失败很常见
            #   （Chrome 冷启动慢、profile 被占、杀软正在扫刚写出的 PNG）——
            #   实测这类抖动是"卡壳"的主要来源，重试一次能救回大部分。
            print("   ↻ 像素门第一次没跑完，自动重试一次…")
            o2, rc2 = run("pipeline.py", spec, "-o", out, *_extra)
            if "measure:" in o2 or rc2 == 0:
                o, rc_pipe = o2, rc2
        pipe_out = o                      # ★ 后面 o 会被 review_sheet 覆盖，先存一份
        # ★ pipeline 崩了必须算硬问题：原来只扫输出里的关键词，脚本抛异常时既没有
        #   measure: 也没有 needs_llm，于是"硬问题 0 处"是**假绿**（实测踩过：
        #   ink.py 被裁坏、palette 未定义，run.py 还报可以交付）
        if rc_pipe != 0 and "measure:" not in o:
            hard.append("像素门｜pipeline 异常退出（exit=%d，重试 1 次后仍失败）：%s"
                        % (rc_pipe, (o.strip().splitlines() or [""])[-1][:110]))

        # ★ 产物核对：渲染失败原来只写进 pipeline 的日志、退出码仍是 0 —— 于是
        #   "8 张里 1 张没出图"会被当成干净交付。这里**独立数一遍文件**，
        #   不信任上游的自我报告（用户遇到的就是这个：图 05 没出来但报告说没问题）。
        try:
            import json as _json2
            _n = len((_json2.load(io.open(spec, encoding="utf-8")).get("cards") or []))
        except (ValueError, IOError):
            _n = 0
        _missing = [("card-%02d" % i) for i in range(1, _n + 1)
                    if not os.path.exists(os.path.join(out, "card-%02d.png" % i))
                    or os.path.getsize(os.path.join(out, "card-%02d.png" % i)) < 1024]
        if _missing:
            hard.append("产物｜以下页没有出图或文件为空（单独返工：run.py <spec> --only N）：%s"
                        % " ".join(_missing))
    # ★ pipeline 的 needs_llm 明细是「缩进的一行一条」，必须整块收进来。
    #   原来只把标题行（"⚠ 以下文案需要 LLM 重写"）记进 hard，逐条明细全丢了 ——
    #   于是结论只剩一句"需要 LLM 重写"，agent 根本不知道改哪句、差多少，
    #   只能回头单独跑一次 pipeline.py 才看得到（实测多花一整轮）。
    _in_llm = _in_soft = False
    for l in o.splitlines():
        s = l.strip()
        if re.search(r"measure:|verify:|降级 |耗时", s):
            print("④ 像素门   " + s)
        if "需要 LLM 重写" in s:
            _in_llm, _in_soft = True, False
            hard.append("像素门｜" + s[:110])
            continue
        if s.startswith("·") and "不影响交付" in s:
            # ★ 孤字提示段落：**不是硬问题**，收进 soft。它原来和 needs_llm 同段，
            #   run.py 只看"需要 LLM 重写"标题就判硬 → 一条孤字提示让整轮 exit=1。
            #   ★ 必须同时判行首的「·」：measure: 那行也带"不影响交付"字样，
            #   只按字样匹配会把后面的 verify:/render: 全吞进来（实测踩过）。
            _in_soft, _in_llm = True, False
            continue
        if _in_llm:
            if s:
                hard.append("像素门｜  " + s[:110])
                continue
            _in_llm = False
        if _in_soft:
            if s and not s.startswith("耗时"):
                soft.append("孤字提示｜" + s[:110])
                continue
            _in_soft = False
        if re.search(r"crosses-|overlap", s):
            hard.append("像素门｜" + s[:120])
        if s.startswith("[") and re.search(r"缩到|密集档|截断", s):
            soft.append(s)

    # ★ 逐页文字体检表：把"四道门已经量过每一页"这件事用文字摊开。
    #   为什么需要：agent 会拿看图当验证手段（实测一轮 8 次、占 68% 墙钟），
    #   文档说不看它也会看；把结论给足，它才没有理由再去花那 40~250 秒。
    import json as _json
    try:
        _spec = _json.load(io.open(spec, encoding="utf-8"))
        _bad = " ".join(hard)
        # ★ 像素门根本没跑时，**不能**打勾。原来只要 hard 里没有 "card-05"
        #   这个字面量就打 ✓ —— 于是超时/崩溃时整排 ✓，看着像"全部通过"，
        #   实际是一页都没量过（和前面那几个假绿同一类错误）。
        if not a.no_render and "measure:" not in pipe_out:
            print("  逐页：**像素门没跑成，一页都没量过** —— 下面的 ✓ 不成立：")
            print("        （原因见结论；修好后重跑本命令即可）")
        else:
            print("  逐页：", end="")
            for i, _c in enumerate(_spec.get("cards") or [], 1):
                tag = "card-%02d" % i
                mark = "✗" if tag in _bad else "✓"
                print("%s%s " % (mark, tag.replace("card-", "")), end="")
            print("（✓ = 该页四道门全过：无溢出/越界/压框/压线/重叠/孤字/断词/截断）")
    except (ValueError, IOError):
        pass

    o = ""
    if not a.no_render:
        o, _ = run("review_sheet.py", out)
    thumbs = re.search(r"(\d+)x", o)
    if a.no_render:
        print("⑤ 复核图   （--no-render：跳过缩略图）")
    else:
        print("⑤ 复核图   " + ([l.strip() for l in o.splitlines() if "真要看观感时" in l]
                                or ["已生成复核缩略图"])[0][:96])

    print("\n" + "=" * 64)
    if hard:
        print("✗ 必须改（%d 处）—— 改完再跑一次本命令即可：" % len(hard))
        for h in hard[:12]:
            print("   " + h)
    else:
        print("✓ 硬问题 0 处 —— 可以交付。")
        print("  **不必再看图**：文字类毛病（溢出/越界/压框/压线/重叠/孤字/断词/数量词/截断）")
        print("  四道门已逐页量过（见上面的逐页表）。看图只对'配色疏密'这类主观项有意义，")
        print("  单次 40~250 秒 —— 想看就只看 1 张封面，并在报告里注明'审美已抽查 1 张'。")
    if soft:
        print("· 提示（%d 处，**不影响交付**、无需改文案）：" % len(soft))
        for s in soft[:6]:
            print("   " + s[:110])
    # ★ 交付报告：数字由脚本填好、格式与 SKILL.md 的模板一致 —— 省掉 agent 自己拼装那一轮
    if not hard:
        try:
            _sp = _json.load(io.open(spec, encoding="utf-8"))
            _cards = _sp.get("cards") or []
            _lays = " / ".join("%02d %s" % (i, c.get("layout")) for i, c in enumerate(_cards, 1))
            _plan = (_sp.get("meta") or {}).get("plan") or {}
            _pl = ("plan.py 建议 %s，区间 %s~%s" % (_plan.get("suggest"),
                                                   (_plan.get("range") or ["?", "?"])[0],
                                                   (_plan.get("range") or ["?", "?"])[1])
                   if _plan.get("suggest") else "meta.plan 未填")
            _deg = [l.strip() for l in pipe_out.splitlines() if l.strip().startswith("[")]
            _meas = [l.strip() for l in pipe_out.splitlines() if "measure:" in l or "verify:" in l or "耗时" in l]
            print("")
            print("交付报告（数字已填好，可直接粘贴）")
            print("  页数：%d 页（%s）" % (len(_cards), _pl))
            print("  版式：%s" % _lays)
            print("  规格门：%s" % ([l.strip() for l in spec_out.splitlines()
                                    if "契约校验" in l or "契约违规" in l]
                                  or ["（有提示，见上）"])[0])
            for _l in _meas:
                print("  像素门：%s" % _l)
            print("  降级报告：%s" % ("%d 处（缩字/密集档，详见上表）" % len(_deg) if _deg
                                    else "无"))
            print("  自检：<待你填> 审美抽查 N 张（或「审美未校验」）")
        except (ValueError, IOError, NameError):
            pass

    print("=" * 64)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())