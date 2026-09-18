# -*- coding: utf-8 -*-
"""preflight.py —— 交付前的**文字级**预检：把"只能看图才发现"的四类毛病变成计算。

为什么要有它（实测代价）：hermes 第 1 轮一篇图 847s，其中光"逐张看图"就烧掉 653s（77%）；
第 2 轮更糟 —— 27 次视觉调用 1587s（83%）。隔离测量：
   720px 单张缩略图一次视觉调用 ≈ **103 秒**
   4 张拼版（1488×2056）一次调用 **>600 秒仍未返回** → 延迟随图片**面积**走
也就是说"复核"这一步的成本由视觉服务的像素量决定，而它要查的毛病里，四类有三类
**根本不需要看图**：

    孤字          → 文案折行结果算得出来（末行占宽 / 字数）
    断词          → 折行算法本来就保证不切拉丁词，这里再验一遍（应当是 0）
    数量词对不上  → 标题里的"两件事 / 三个坑 / 4 个变化"和实际条数比一比
    压字 / 出框   → 像素门已经用 getBBox 实测过了（本脚本不重复）
    配色 / 疏密   → **这一类才真的需要看图**，而且是主观判断，可选

用法：
    python scripts/preflight.py <spec.json>
    python scripts/preflight.py <spec.json> --json
退出码：0 = 没发现文字级问题；1 = 有（改完再审）
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import ink  # noqa: E402

CN_NUM = {"一": 1, "两": 2, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7,
          "八": 8, "九": 9, "十": 10}
QUANT = r"(?:个|条|种|件|步|块|点|层|类|档|问|坑|件事|条线|部分)"
LIST_SLOTS = ("items", "steps", "nodes", "levels", "cells", "stages", "chips", "bottom", "ends")


def load_spec(p):
    raw = io.open(p, encoding="utf-8").read()
    if p.lower().endswith(".json"):
        return json.loads(raw)
    import yaml
    return yaml.safe_load(raw)


def num_in(text):
    """从标题/副标题/备注里抓"两件事 / 3 个坑 / 四步"这类数量词。"""
    hits = []
    for m in re.finditer(r"([0-9]+|[一二两三四五六七八九十])\s*" + QUANT, text or ""):
        tok = m.group(1)
        hits.append((int(tok) if tok.isdigit() else CN_NUM.get(tok, 0), m.group(0)))
    return hits


def items_count(card):
    """这张卡实际有几条并列项（取最像"列表"的那个槽）。"""
    best = 0
    for k in LIST_SLOTS:
        v = card.get(k)
        if isinstance(v, list) and len(v) > best:
            best = len(v)
    for side in ("left", "right"):
        v = (card.get(side) or {}).get("blocks") if isinstance(card.get(side), dict) else None
        if isinstance(v, list) and len(v) > best:
            best = len(v)
    for q in card.get("quads") or []:
        if isinstance(q, dict) and isinstance(q.get("items"), list) and len(q["items"]) > best:
            best = len(q["items"])
    return best


def check(spec):
    meta = dict(spec.get("meta") or {})
    cards = spec.get("cards") or []
    font = "file:///" + os.path.join(ROOT, "assets", "fonts",
                                     "ZCOOLKuaiLe-Regular.ttf").replace("\\", "/")
    out = []
    for i, card in enumerate(cards, 1):
        page = "card-%02d(%s)" % (i, card.get("layout"))
        ink.render_card(card, i - 1, len(cards), meta, font)   # 副作用：填 _CAPS
        slots = [dict(c) for c in ink._CAPS]

        # ① 孤字 / ③ 断词：从折行结果算
        for s in slots:
            text, size, maxw, ml = s["text"], s["size"], s["maxw"], s["max_lines"]
            if not text or ml <= 1:
                continue
            lines = ink.wrap_text(text, size, maxw)
            if len(lines) < 2:
                continue
            last_w = ink.tw(lines[-1].strip(), size)
            # 孤字：末行只剩 1~2 个字，或占宽不到 20%（'私有化' 那种 3 字 28% 不算）
            if len(lines[-1].strip()) <= 2 or last_w < 0.2 * maxw:
                out.append({"page": page, "tag": s["tag"], "kind": "孤字",
                            "detail": "折 %d 行，末行只剩 %r（占宽 %.0f%%）"
                                      % (len(lines), lines[-1].strip(), 100 * last_w / maxw),
                            "text": text[:40]})
            for a, b in zip(lines, lines[1:]):
                ma, mb = re.search(r"[A-Za-z0-9_\-]+$", a), re.match(r"[A-Za-z0-9_\-]+", b)
                if ma and mb and (ma.group(0) + mb.group(0)) in text:
                    out.append({"page": page, "tag": s["tag"], "kind": "断词",
                                "detail": "%s | %s" % (ma.group(0), mb.group(0)),
                                "text": text[:40]})

        # ② 数量词 vs 实际条数 —— **只看 title**，且跳过「第 N 条」这类序数引用。
        # 扫 subtitle/note 会误伤："一个最小例子" / "拿一点召回" / "两条理由" 都不是在数条目。
        n = items_count(card)
        if n >= 2 and card.get("title"):
            title = str(card["title"])
            for v, tok in num_in(title):
                if not v or v == n or v == 1:
                    # v == 1 一律跳过：「一个最小例子」「拿一点召回」这类是在打比方，不是在数条目
                    continue
                if re.search(r"第\s*" + re.escape(tok), title):     # 「第 3 条」是引用不是计数
                    continue
                out.append({"page": page, "tag": "title", "kind": "数量词待确认",
                            "detail": "标题写「%s」= %d，这一页实际有 %d 条并列项"
                                      % (tok, v, n),
                            "text": title.strip()[:40]})
        # ④ 贴边（>90%）提示
        for s in slots:
            if s["maxw"] and ink.tw(s["text"], s["size"]) / s["maxw"] > 0.9:
                out.append({"page": page, "tag": s["tag"], "kind": "贴边",
                            "detail": "占宽 %.0f%%" % (100 * ink.tw(s["text"], s["size"]) / s["maxw"]),
                            "text": s["text"][:40]})
    return out


def main():
    ap = argparse.ArgumentParser(description="交付前文字级预检（不需要看图）")
    ap.add_argument("spec")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    found = check(load_spec(a.spec))
    if a.json:
        print(json.dumps(found, ensure_ascii=False, indent=1))
        return 1 if found else 0

    hard = [f for f in found if f["kind"] in ("孤字", "断词")]
    soft = [f for f in found if f["kind"] in ("贴边", "数量词待确认")]
    print("文字级预检：%d 页 / 发现 %d 处（其中需处理 %d 处，贴边提示 %d 处）"
          % (len(load_spec(a.spec).get("cards") or []), len(found), len(hard), len(soft)))
    for f in hard:
        print("  ✗ %-20s [%-10s] %-8s %s｜%s"
              % (f["page"], f["tag"], f["kind"], f["detail"], f["text"]))
    for f in soft:
        print("  · %-20s [%-10s] %-8s %s｜%s"
              % (f["page"], f["tag"], f["kind"], f["detail"], f["text"]))
    if not found:
        print("  ✓ 孤字 / 断词 / 数量词 三类都没问题")
    print("\n说明：压字·出框由像素门（measure）实测，配色·疏密才需要看图 —— "
          "而看图很贵（实测 720px 单张一次调用 ~103s，拼版更慢），所以只在"
          "「想看观感」时抽查 1~2 张。")
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())