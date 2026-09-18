# -*- coding: utf-8 -*-
"""plan.py —— 一篇文章该切几页？脚本给答案，别让模型自己推。

为什么需要它：页数规则原本散在 4 个文件、17 处，还带两条修正，冲突时"以谁为准"
文档也没写 —— 实测 agent 为此纠结半天（推理 token 就这么烧掉）。这里把它变成一次计算。

公式（唯一定义在 SKILL.md 第 2 步）：
    张数 ≈ 1（封面）+ 章节数
    修正① 平均每节 < 400 汉字 → 两节并一页
    修正② 全篇 < 1.5k 汉字 → 压到 4~5 张
    区间   4~9（6~9 是小红书平台偏好区）；>12 该拆系列

用法
    python scripts/plan.py <article.md>
    python scripts/plan.py <article.md> --json      # 机器读
"""
import argparse
import io
import json
import re
import sys

THIN = 80          # 少于这么多汉字的二级节算"薄节"（写在前面 / 小结 这类）
AVG_PAIR = 400     # 平均每节汉字数低于它 → 两节并一页
SHORT = 1500       # 全篇汉字数低于它 → 压到 4~5 张
LO, HI = 4, 9      # 平台推荐区间（6~9 偏好，4~5 给短帖）


def cjk(s):
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def sections_of(text):
    """切出二级节（## 开头）及其汉字数。返回 [(标题, 汉字数)]。"""
    out, cur_title, cur_body = [], None, []
    for line in text.splitlines():
        m = re.match(r"^##\s+(.*)$", line)
        if m:
            if cur_title is not None:
                out.append((cur_title, cjk("\n".join(cur_body))))
            cur_title, cur_body = m.group(1).strip(), []
        elif cur_title is not None:
            cur_body.append(line)
    if cur_title is not None:
        out.append((cur_title, cjk("\n".join(cur_body))))
    return out


def plan(article):
    total = cjk(article)
    secs = sections_of(article)
    # ★ 薄节（写在前面 / 小结）**照样算一节** —— 它们通常能独立成页，或自然并到相邻页；
    # 早先按"≥80 汉字才算"过滤掉，会把 4 节的文章算成 3 节，页数少一张（实测对不上）。
    n = len(secs) or 1
    avg = total / float(n)

    content = n
    note1 = "平均每节 %.0f 汉字 ≥ %d → 一节一页" % (avg, AVG_PAIR)
    if avg < AVG_PAIR:
        content = (n + 1) // 2
        note1 = "平均每节 %.0f 汉字 < %d → **两节并一页**（%d 节 → %d 页）" % (avg, AVG_PAIR, n, content)

    cards = 1 + content
    note2 = "全篇 %d 汉字 ≥ %d → 不做压缩" % (total, SHORT)
    lo, hi = LO, HI
    if total < SHORT:
        lo, hi = 4, 5
        cards = min(max(cards, lo), hi)
        note2 = "全篇 %d 汉字 < %d → **压到 %d~%d 张**（公式给 %d，取区间内）" % (total, SHORT, lo, hi, 1 + content)
    cards = min(cards, 12)

    # 页骨架：按合并规则分组
    groups = []
    if avg < AVG_PAIR:
        for i in range(0, len(secs), 2):
            groups.append(secs[i:i + 2])
    else:
        for s in secs:
            groups.append([s])

    return {
        "total_cjk": total,
        "sections": secs,
        "solid_sections": len(secs),
        "avg_cjk": round(avg),
        "suggest_cards": cards,
        "range": [lo, hi],
        "note1": note1,
        "note2": note2,
        "groups": groups,
        "thin": [s[0] for s in secs if s[1] < THIN],
    }


def main():
    ap = argparse.ArgumentParser(description="页数规划：脚本给答案")
    ap.add_argument("article")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    art = io.open(args.article, encoding="utf-8").read()
    p = plan(art)
    if args.json:
        print(json.dumps(p, ensure_ascii=False, indent=1))
        return 0

    print("文章：%s" % args.article)
    print("规模：%d 汉字 / 二级节 %d 个（其中 ≥%d 汉字的实节 %d 个）"
          % (p["total_cjk"], len(p["sections"]), THIN, p["solid_sections"]))
    print("")
    print("每节规模：")
    for t, c in p["sections"]:
        flag = "（薄节，并入相邻页）" if c < THIN else ""
        print("  %5d 汉字  %s%s" % (c, t, flag))
    print("")
    print("判定：")
    print("  · %s" % p["note1"])
    print("  · %s" % p["note2"])
    print("")
    print("→ **建议 %d 张**（区间 %d~%d）" % (p["suggest_cards"], p["range"][0], p["range"][1]))
    print("")
    print("页骨架（第 1 页固定是 cover 封面）：")
    print("  card-01  cover")
    for i, g in enumerate(p["groups"], 2):
        titles = " + ".join(t for t, _ in g)
        chars = sum(c for _, c in g)
        print("  card-%02d  %s（%d 汉字）" % (i, titles[:46], chars))
    print("")
    print("版式自己挑（看 [docs/layouts.md] 的对照表）；主题数就是上面的分组数。")
    return 0


if __name__ == "__main__":
    sys.exit(main())