# -*- coding: utf-8 -*-
"""capacity.py —— 别问契约，直接问引擎：这个槽到底放得下多少字。

为什么需要它：契约里那 81 个手写上限只是**建议值**，真实容量由几何决定
（可用宽 ÷ 字号，还要看允许几行）。`arch` 的 chip 是活例：契约写 ≤6，
但 4 个 chip 时每格只有 179px、字号 44 → 真实只放得下约 3.7 个汉字，
于是"规格门绿、像素门连烧 3 轮"。

做法：把每张卡在内存里渲染一遍（不需要浏览器），读引擎落字时登记的几何
（`ink._CAPS` = 折行前原文 + 设计字号 + 可用宽 + 行数上限），据此判定：

    ok        标准字号就放得下
    dense     标准放不下、小一号字（×0.85）放得下 —— 会走密集档，建议改短
    overflow  连密集档都放不下 —— **必须改短/换版式**（这才是真墙）

用法
    python scripts/capacity.py spec/xxx.json            # 人读：非 ok 的槽 + 汇总
    python scripts/capacity.py spec/xxx.json --all      # 连 ok 的也列出来
    python scripts/capacity.py spec/xxx.json --json     # 机器读（含原始几何）
    python scripts/capacity.py spec/xxx.json --budget   # 每槽字数预算表（**写文案前**先看）
"""
import argparse
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ink  # noqa: E402


def load_spec(path):
    raw = io.open(path, encoding="utf-8").read()
    if path.lower().endswith(".json"):
        return json.loads(raw)
    try:
        import yaml
    except ImportError:
        raise SystemExit("读 YAML 需要 pyyaml：pip install pyyaml")
    return yaml.safe_load(raw)


def _cjk_len(s):
    """汉字口径长度：汉字/全角标点 = 1，其余（拉丁/数字/空格）= 0.5。
    `[[高亮]]` 标记本身不计（用 ink.strip_hl 去掉）。"""
    return sum(1.0 if ord(c) > 0x2E80 else 0.5 for c in ink.strip_hl(s or ""))


def judge(entry):
    """按登记到的几何判定一个槽：ok / dense / overflow。"""
    text, size, maxw = entry["text"], entry["size"], entry["maxw"]
    max_lines = entry["max_lines"]
    out = dict(entry)
    out["w_std"] = round(ink.tw(text, size), 1)
    out["w_dense"] = round(ink.tw(text, size * ink.DENSE), 1)
    if max_lines <= 1:
        out["lines_std"] = out["lines_dense"] = 1
        fits_std = out["w_std"] <= maxw
        fits_dense = out["w_dense"] <= maxw
    else:
        out["lines_std"] = len(ink.wrap_text(text, size, maxw))
        out["lines_dense"] = len(ink.wrap_text(text, size * ink.DENSE, maxw))
        fits_std = out["lines_std"] <= max_lines
        fits_dense = out["lines_dense"] <= max_lines
    # 反推"放得下多少字"：纯汉字口径（拉丁按 0.62 折）
    unit = max(1.0, size * ink.CALIB[0])
    out["cap_chars"] = int(maxw / unit) * max_lines
    out["verdict"] = "ok" if fits_std else ("dense" if fits_dense else "overflow")
    # 严重度：真丢字（多行被截）或缩到不可读（<28px）才算硬；只是变小变挤只提示
    out["shrink_to"] = size if fits_std else max(20, int(size * maxw / max(1.0, out["w_std"])))
    if out["verdict"] == "dense":
        out["severity"] = "warn"
    elif out["verdict"] == "overflow":
        # ★ 只有**多行**放不下才是硬问题：那意味着引擎会把尾巴截成「…」= 丢字。
        #   单行放不下只是"缩字"——引擎保证不出框、不丢字，改文案纯属浪费一轮 LLM
        #   （实测：为适配反复改文案是慢的主因）。
        out["severity"] = "hard" if max_lines > 1 else "warn"
    else:
        out["severity"] = "ok"
    return out


def scan(spec):
    """逐卡渲染（不启浏览器）→ 读 ink._CAPS → 判定。"""
    meta = dict(spec.get("meta") or {})
    cards = spec.get("cards") or []
    font = "file:///" + os.path.join(ROOT, "assets", "fonts", "ZCOOLKuaiLe-Regular.ttf").replace("\\", "/")
    pages = []
    for i, card in enumerate(cards):
        ink.render_card(card, i, len(cards), meta, font)      # 副作用：填 _CAPS / _SLOTS
        entries = [judge(e) for e in list(ink._CAPS)]
        # DOM 槽（flow/chain/compare 已迁移）：它们的"预算"就是槽尺寸 + 起手字号，
        # 缩多少由浏览器的 autofit 实测决定 —— 不在这里估算
        # ★ 但**必须给个「约 N 字」**：只给尺寸、不给字数的表，写文案时等于没有参考
        #   （实测：compare 每列 3 block + 1 note 时 block 只剩约 6 字，看不到就会写到 9 字）。
        #   这只是几何估算，所以**不下 verdict**，避免误报"必须改短"又把 agent 拉回来改文案。
        _unit = max(1.0, ink.CALIB[0])

        def _cap(w, size, clamp):
            """槽宽 ÷ 字号 × 行数 = 约几个汉字。"""
            return int(w / max(1.0, size * _unit)) * max(1, clamp)

        dom = [{"tag": "dom", "text": sl["text"], "size": sl["size"], "maxw": sl["w"],
                "max_lines": sl["clamp"], "verdict": "dom",
                # 「舒适」= 起手字号就放得下；「下限」= 浏览器 autofit 缩到 min_size 还能放
                # （_reg_slot 的 min_size = max(12, size*0.55)）。判定用**下限**，
                # 因为浏览器本来就会缩字号 —— 拿起手字号判会刷一堆误报（实测 18 条里误报 6 条）。
                "cap_chars": _cap(sl["w"], sl["size"], sl["clamp"]),
                "cap_floor": _cap(sl["w"], max(12, int(sl["size"] * 0.55)), sl["clamp"]),
                "w_std": 0, "lines_std": 0, "w": sl["w"], "h": sl["h"]}
               for sl in list(ink._SLOTS)]
        pages.append({"page": "card-%02d" % (i + 1), "layout": card.get("layout"),
                      "slots": entries, "dom": dom})
    return pages


def main():
    ap = argparse.ArgumentParser(description="几何容量：这个槽到底放得下多少字")
    ap.add_argument("spec")
    ap.add_argument("--all", action="store_true", help="连放得下的也列出来")
    ap.add_argument("--budget", action="store_true",
                    help="打印每槽字数预算表（写文案之前先看这个，别写完才发现放不下）")
    ap.add_argument("--json", action="store_true", help="输出 JSON（机器读）")
    args = ap.parse_args()

    pages = scan(load_spec(args.spec))
    if args.json:
        print(json.dumps(pages, ensure_ascii=False, indent=1))
        return 0

    bad = [s for p in pages for s in p["slots"] if s["verdict"] != "ok"]
    tight = [s for p in pages for s in p["slots"]
             if s["verdict"] == "ok" and s["maxw"] and s["w_std"] / s["maxw"] > 0.9]
    total = sum(len(p["slots"]) for p in pages)
    n_dom = sum(len(p.get("dom") or []) for p in pages)

    print("几何容量（%d 页 / %d 个文字槽；不是契约上的建议值，是引擎实测的几何）"
          % (len(pages), total))
    print("")
    if bad:
        print("★ 标准字号放不下的槽 %d 个：" % len(bad))
        for p in pages:
            for s in p["slots"]:
                if s["verdict"] == "ok":
                    continue
                if s["verdict"] == "overflow":
                    why = ("多行：%d 行 > 上限 %d 行（会被截成「…」）"
                           % (s["lines_std"], s["max_lines"]) if s["max_lines"] > 1
                           else "单行超宽 %.0f%%（会被强行缩字）"
                                % (100 * s["w_std"] / s["maxw"] - 100))
                    tag = "必须改短" if True else ""
                else:
                    why = "小一号字还能放下（走密集档，视觉上略小）"
                    tag = ""
                print("  %s(%s)  %-12s [%s] %s｜%s"
                      % (p["page"], p["layout"], s["tag"], why.split("（")[0],
                         s["verdict"], s["text"][:30]))
                print("      注意：%s" % why)
    elif n_dom:
        # ★ 这里**不能**报"都放得下"：文字槽已全部迁到 DOM，`_CAPS` 恒为空表，
        #   于是这个分支其实**一个槽都没判过** —— 报"✓"就是假绿。
        #   实测踩过：--budget 报「所有槽在标准字号下都放得下 ✓」，
        #   紧接着真跑 pipeline 就是 3 处 dom-overflow，白信它一轮。
        print("★ 没有可判定的槽：文字已全部迁到 DOM（%d 个槽），折行/缩放由浏览器决定。"
              % n_dom)
        print("  真实结论只能跑：python scripts/run.py <spec.json> --no-render")
        print("  下表里的「约 N 字」是按槽宽 ÷ 字号估的，写文案时拿它当参考线。")
    else:
        print("★ 所有槽在标准字号下都放得下 ✓")
    if tight:
        print("\n⚠ 已经贴到边（宽度 >90%%）的槽 %d 个，改动文案时留意：" % len(tight))
        for s in tight[:8]:
            print("  [%s] %s（%.0f%%）｜%s" % (s["tag"], s["verdict"],
                                             100 * s["w_std"] / s["maxw"], s["text"][:24]))
    print("\n口径：ok=%d / dense=%d / overflow=%d（槽位合计 %d）"
          % (sum(1 for p in pages for s in p["slots"] if s["verdict"] == "ok"),
             sum(1 for p in pages for s in p["slots"] if s["verdict"] == "dense"),
             sum(1 for p in pages for s in p["slots"] if s["verdict"] == "overflow"), total))
    if args.budget:
        print("\n=== 每槽字数预算表（写文案前先看；越紧的越在上面）===")
        print("    汉字口径：1 个汉字 = 1em，拉丁字母约 0.62em；行数按允许的最大行数算")
        rows = [s for p in pages for s in p["slots"]]
        rows.sort(key=lambda s: s["cap_chars"])
        for s in rows:
            tight = "紧" if s["maxw"] and s["w_std"] / s["maxw"] > 0.9 else "  "
            print("  %s %-11s 约 %3d 字 / %d 行  字号 %2d  可用宽 %4.0f  ｜%s"
                  % (tight, s["tag"], s["cap_chars"], s["max_lines"], s["size"],
                     s["maxw"], s["text"][:22]))
        print("  提示：表中的字数是**建议值**；标准字号放不下就会走密集档（小一号字），"
              "再放不下才必须改短。")

        doms = [d for p in pages for d in (p.get("dom") or [])]
        if doms:
            print("\n=== DOM 文字槽（折行/缩放由浏览器负责；「约 N 字」是按槽宽÷字号估的参考线）===")
            doms.sort(key=lambda d: d["cap_floor"])          # 越紧的越在上面
            for d in doms[:18]:
                n = _cjk_len(d["text"])
                flag = " ⚠超下限" if n > d["cap_floor"] + 0.5 else "        "
                print("     槽 %4.0fx%-4.0f 字号 %2d 行%d ｜约 %2d 字（缩到下限 %2d 字）%s｜%s"
                      % (d["w"], d["h"], d["size"], d["max_lines"],
                         d["cap_chars"], d["cap_floor"], flag, d["text"][:20]))
            if len(doms) > 18:
                print("     …共 %d 个槽（只列最窄的 18 个）" % len(doms))
            print("  注：「约 N 字」是几何估算，不是判定。浏览器会先缩字号兜住，所以只有"
                  "超过**下限**才标 ⚠；真放不下以 run.py 的像素门为准。")

    if args.all:
        print("\n=== 全部槽 ===")
        for p in pages:
            for s in p["slots"]:
                print("  %s %-12s %-8s 宽 %.0f/%.0f 行 %d/%d ｜%s"
                      % (p["page"], s["tag"], s["verdict"], s["w_std"], s["maxw"],
                         s["lines_std"], s["max_lines"], s["text"][:26]))
    return 1 if any(s["verdict"] == "overflow" for s in bad) else 0


if __name__ == "__main__":
    sys.exit(main())