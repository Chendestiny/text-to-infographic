# -*- coding: utf-8 -*-
"""方框样式比选：固定「版式 + 规格」，只换**皮肤**与**节点框画法**，拼成对照表。

    python make_style_probe.py                                   # 默认：4 套工程皮肤 × A/G 两案
    python make_style_probe.py --layout bullets
    python make_style_probe.py --themes terminal --styles A,B,C,D
    python make_style_probe.py --themes grid,retro --styles B

为什么要有它：调节点外观时直接改 `theme.py` 再跑整套图鉴，
**变的不只是方框**（版式内容一换，判断就被搅浑）。
这里把皮肤与版式钉死，只扫 `node_style` / `node_radius` / `node_line` 这几个令牌。

产出到桌面 `t2i-box-styles/`：每格一张 1080×1440 原图 + 一张对照拼版。
排版：**列 = 皮肤，行 = 方框方案**（同一列上下对比，就是同一皮肤换框）。
挑定后改 `scripts/theme.py` 里那一行 `node_style`（或整组令牌）即可。
"""
import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "scripts"))
import ink      # noqa: E402
import sheet    # noqa: E402
import theme    # noqa: E402
from render import find_browser, shoot, file_url  # noqa: E402

FONT = file_url(os.path.join(HERE, "assets", "fonts", "ZCOOLKuaiLe-Regular.ttf"))
BUILD = os.path.join(HERE, "build", "box-style-html")

# 方框方案：字母 → (覆盖令牌, 一句话)。第二行**必须短**，格子只有 ~19 字宽
PRESETS = {
    "A": ("纯细线", {"node_style": "none"}, "只有一道主题色细线"),
    "B": ("角块", {"node_style": "tab"}, "左上角彩色小方块"),
    "C": ("左竖轨", {"node_style": "rail"}, "左侧彩色短竖轨"),
    "D": ("顶线", {"node_style": "rule"}, "顶边左起一段短线"),
    "E": ("直角", {"node_style": "tab", "node_radius": 0}, "角块 + 去圆角，更硬朗"),
    "F": ("双线框", {"node_style": "double"}, "内外双线，最像图纸"),
    "G": ("四角刻度", {"node_style": "corner"}, "四角各一对短刻度，像取景框"),
    "H": ("中性色框", {"node_style": "tab", "node_line": "#5A6B8C"}, "描边换成中性灰蓝（反面样本）"),
}

CARDS = {
    "chain": {"layout": "chain", "title": "Function Calling",
              "subtitle": "[[tool_call]] 是模型吐的，干活的是代码",
              "steps": [{"text": "① 注入 [[tools 定义]]"},
                        {"text": "② 模型返回 tool_calls"},
                        {"text": "③ 你的代码执行"},
                        {"text": "④ 结果 [[塞回历史]]"}],
              "note": "回到 ② 步，直到模型不再调工具"},
    "bullets": {"layout": "bullets", "title": "主动砍 token 的三刀",
                "subtitle": "token 就是钱，[[每一行都按 token 计价]]",
                "items": [{"no": "①", "head": "砍工具原文保结论", "desc": "结果先消化成一句话，再进窗口。"},
                          {"no": "②", "head": "砍历史保摘要", "desc": "十轮对话压成五行要点。"},
                          {"no": "③", "head": "检索结果标来源", "desc": "标明出处和适用范围。"}]},
    "matrix": {"layout": "matrix", "title": "向量库按规模挑",
               "subtitle": "先用最简单的跑通，[[真撞到瓶颈再换]]",
               "labels": {"top": "数据量从小到大"},
               "cells": [{"head": "十万级", "desc": "chroma 本地玩具"},
                         {"head": "百万千万", "desc": "pgvector / Qdrant"},
                         {"head": "十亿级", "desc": "Pinecone 全托管"},
                         {"head": "百亿级", "desc": "Milvus 分布式"}]},
}

DIAGRAM = ["terminal", "blueprint", "mono", "nord"]


def _desktop():
    for d in ("Desktop", "桌面"):
        p = os.path.join(os.path.expanduser("~"), d)
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def main():
    ap = argparse.ArgumentParser(description="方框样式比选（固定版式，只扫皮肤与节点令牌）")
    ap.add_argument("--themes", default=",".join(DIAGRAM), help="逗号分隔（默认 4 套工程皮肤）")
    ap.add_argument("--styles", default="A,G", help="方框方案字母，逗号分隔（默认 A,G）")
    ap.add_argument("--layout", default="chain", choices=sorted(CARDS))
    ap.add_argument("-o", "--out", default=os.path.join(_desktop(), "t2i-box-styles"))
    ap.add_argument("--scale", type=int, default=1)
    a = ap.parse_args()

    keys = [s.strip() for s in a.themes.split(",") if s.strip()]
    styles = [s.strip().upper() for s in a.styles.split(",") if s.strip()]
    for k in keys:
        if k not in theme.THEMES:
            sys.exit("未知皮肤 %r" % k)
    for s in styles:
        if s not in PRESETS:
            sys.exit("未知方案 %r（可用：%s）" % (s, "/".join(sorted(PRESETS))))

    base = {k: dict(theme.THEMES[k]) for k in keys}
    card = CARDS[a.layout]
    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)
    browser = find_browser()
    print("皮肤：%s\n方案：%s\n版式：%s\n输出：%s\n" % (", ".join(keys), ", ".join(styles), a.layout, out))

    pngs, labels, failed = [], [], []
    for s in styles:                     # 行 = 方案，列 = 皮肤
        cn, over, why = PRESETS[s]
        for k in keys:
            T = theme.THEMES[k]
            T.clear()
            T.update(base[k])
            T.update(over)
            html = ink.render_card(card, 1, 3, {"theme": k}, FONT)
            hp = os.path.join(BUILD, "%s-%s-%s.html" % (a.layout, k, s))
            io.open(hp, "w", encoding="utf-8").write(html)
            png = os.path.join(out, "%s-%s-%s.png" % (a.layout, s, k))
            ok, msg = shoot(browser, hp, png, 1080, 1440, a.scale)
            print("  %-2s %-10s %-14s %s" % (s, k, cn, msg))
            if ok:
                pngs.append(png)
                labels.append("%s · %s（%s）\n%s"
                              % (k, s, cn, why + "；线宽 %.1f" % float(T.get("node_w") or 0)))
            else:
                failed.append(png)

    p = sheet.contact_sheet(pngs, os.path.join(out, "对照-%s.png" % a.layout),
                            cols=len(keys), thumb_w=360,
                            title="方框样式比选 · %s（列=皮肤，行=方框方案）" % a.layout,
                            note="同一版式、同一条规格",
                            labels=labels)
    print("\n对照表：%s" % p)
    if failed:
        print("失败 %d 张" % len(failed))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
