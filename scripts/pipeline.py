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


# ---------------------------------------------------------------- 节点
def node_build(state):
    """规格 → HTML（calib 会随迭代更新，tw() 越跑越准）。"""
    meta = dict(state["meta"])
    meta["calib"] = state["calib"]
    ink.CALIB[0] = state["calib"]
    outdir = state["build_dir"]
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    else:
        # 清掉上一次的卡片：规格从 9 页缩到 8 页时，残留的 card-09.html
        # 会被 render 当成第 9 张一起渲染出去（实测踩过）
        for f in os.listdir(outdir):
            if f.startswith("card-") and f.endswith(".html"):
                os.remove(os.path.join(outdir, f))
    for i, card in enumerate(state["cards"]):
        html = ink.render_card(card, i, len(state["cards"]), meta, state["font_url"])
        with io.open(os.path.join(outdir, "card-%02d.html" % (i + 1)), "w",
                     encoding="utf-8") as f:
            f.write(html)
    state["log"].append("build: %d 页（calib=%.2f）" % (len(state["cards"]), state["calib"]))


def node_measure(state):
    """逐页真实测量，收集溢出。"""
    issues = {}
    for i in range(len(state["cards"])):
        hp = os.path.join(state["build_dir"], "card-%02d.html" % (i + 1))
        rep, iss = measure_and_analyze(hp, state["browser"])
        if iss:
            issues["card-%02d" % (i + 1)] = iss
    state["issues"] = issues
    total = sum(len(v) for v in issues.values())
    state["log"].append("measure: %d 处溢出" % total)


def node_verify(state):
    """条件边：干净 → render；有溢出 → 分流。"""
    width_issues = {}
    layout_issues = []
    for page, lst in state["issues"].items():
        for i in lst:
            if (i["kind"] == "out-of-canvas" and i.get("where") == "y") \
                    or i["kind"] in ("v-overflow", "missing-text"):
                # 版式 / 内容问题，脚本修不了：v-overflow 要减条数或拆页，
                # missing-text 是引擎把字吞了，必须让人（或 Agent）看
                layout_issues.append((page, i))
            else:
                width_issues.setdefault(page, []).append(i)
    state["width_issues"] = width_issues
    state["layout_issues"] = layout_issues


def node_autofix(state):
    """确定性修正：校准因子放大 + 对溢出的 SVG 文本注入 textLength。"""
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
    else:
        # 同样清掉旧图：页数变少时残留的 card-07..09.png 会冒充新产物
        for f in os.listdir(state["out_dir"]):
            if f.startswith("card-") and f.endswith(".png"):
                os.remove(os.path.join(state["out_dir"], f))
    for i in range(len(state["cards"])):
        hp = os.path.join(state["build_dir"], "card-%02d.html" % (i + 1))
        png = os.path.join(state["out_dir"], "card-%02d.png" % (i + 1))
        ok, msg = shoot(browser, hp, png, 1080, 1440, 2)
        state["log"].append("render: %s %s" % (os.path.basename(png), msg))


# ---------------------------------------------------------------- 图
def run(spec_path, out_dir, frame=None, no_decor=False, verbose=True):
    t0 = time.perf_counter()
    state = {
        "spec": spec_path, "meta": {}, "calib": 1.0, "issues": {},
        "log": [], "browser": find_browser(),
        "font_url": file_url(os.path.join(ROOT, "assets", "fonts",
                                          "ZCOOLKuaiLe-Regular.ttf")),
        "build_dir": os.path.join(ROOT, "build", os.path.splitext(
            os.path.basename(spec_path))[0]),
        "out_dir": os.path.abspath(out_dir),
    }
    spec = _load(spec_path)
    state["cards"] = spec.get("cards") or []
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
        if it == MAX_ITER:
            state["log"].append("verify: %d 轮后仍有溢出，标记给 LLM 重写文案"
                                % MAX_ITER)
            state["needs_llm"] = [(p, i["text"]) for p, lst in
                                  state["width_issues"].items() for i in lst]
            state["needs_llm"] += [(p, i["text"]) for p, i in state["layout_issues"]]
            break
        node_autofix(state)
        node_build(state)
    node_render(state)

    if verbose:
        for line in state["log"]:
            print("  " + line)
        if state.get("needs_llm"):
            print("\n  ⚠ 以下文案需要 LLM 重写（脚本压不下了）：")
            for p, t in state["needs_llm"]:
                print("    %s  「%s」" % (p, t))
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
    args = ap.parse_args()
    st = run(args.spec, args.out, frame=args.frame, no_decor=args.no_decor)
    print("\n耗时 %.1fs" % st["seconds"])
    sys.exit(0)
