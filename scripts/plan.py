# -*- coding: utf-8 -*-
"""plan.py —— 一篇文章该切几页？脚本给答案，别让模型自己推。

为什么需要它：页数规则原本散在 4 个文件、17 处，还带两条修正，冲突时"以谁为准"
文档也没写 —— 实测 agent 为此纠结半天（推理 token 就这么烧掉）。这里把它变成一次计算。

**两级切页**（第一版只按 `##` 切，被实测打回）：章节很重时（≥600 汉字）只切到章
会把 688 / 885 汉字硬压进一页，必须丢内容 —— 实测 hermes 因此推翻脚本的 5 张、
自己重算成 8 张。现在重章节直接按 `###` 子节切，每页目标 ~300 汉字，
输出的页骨架就是可以直接照抄的。

公式（唯一定义在 SKILL.md 第 2 步）：
    张数 ≈ 1（封面）+ 内容页
    轻章节（<600 汉字）：平均每节 <400 汉字 → 两节并一页
    重章节（≥600 汉字）：按 ~300 汉字/页 切，尽量落在 `###` 子节边界
    区间 4~9（6~9 是平台偏好区）；>12 拆系列

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
AVG_PAIR = 400     # 轻章节平均每节汉字数低于它 → 两节并一页
HEAVY = 600        # 章节达到这么多汉字 → 按子节切
PAGE_TARGET = 300  # 重章节里每页的目标汉字数
SHORT = 1500       # 全篇汉字数低于它 → 压到 4~5 张
LO, HI = 4, 9      # 平台推荐区间（6~9 偏好，4~5 给短帖）


def cjk(s):
    return len(re.findall(r"[\u4e00-\u9fff]", s))


def split_sections(text, level):
    """按 markdown 层级切块。level=2 → `##`，level=3 → `###`。返回 [(标题, 正文)]。"""
    out, title, body = [], None, []
    pat = re.compile(r"^%s\s+(.*)$" % ("#" * level))
    for line in text.splitlines():
        m = pat.match(line)
        if m:
            if title is not None:
                out.append((title, "\n".join(body)))
            title, body = m.group(1).strip(), []
        elif title is not None:
            body.append(line)
    if title is not None:
        out.append((title, "\n".join(body)))
    return out


KEY_RE = re.compile(r"\*\*|重点|关键|核心|必看|★")


def pack(chunks, target):
    """把若干块按目标字数打包成页（尽量不跨块切）。chunks = [(标题, 汉字数)]

    ★ 带重点标记的子节（`**` / 重点 / 关键 / 核心 / 必看 / ★）**单独成页**：
    实测 agent 会因为这些被合并而推翻脚本（原文自己标了重点，合并就是丢重点）。
    """
    pages, cur = [], []
    for t, c in chunks:
        if KEY_RE.search(t) and cur:          # 重点块不跟别人挤
            pages.append(cur)
            cur = []
        cur.append((t, c))
        if KEY_RE.search(t) or sum(x[1] for x in cur) >= target:
            pages.append(cur)
            cur = []
    if cur:
        pages.append(cur)
    return pages


def plan(article):
    total = cjk(article)
    secs = [(t, cjk(b)) for t, b in split_sections(article, 2)]
    bodies = dict(split_sections(article, 2))          # 标题 -> 正文（用来取子节）
    if not secs:
        secs = [("(全文)", total)]
        bodies = {"(全文)": article}

    # ---- 逐章决定切法 ----
    heavy = [s for s in secs if s[1] >= HEAVY]
    light = [s for s in secs if s[1] < HEAVY]
    groups = []          # 每页 = [(标题, 汉字数), ...]
    notes = []

    for title, chars in heavy:
        subs = [(t, cjk(b)) for t, b in split_sections(bodies.get(title, ""), 3)]
        subs = [s for s in subs if s[1] >= 20] or [(title, chars)]
        target = max(PAGE_TARGET, round(chars / max(1, round(chars / PAGE_TARGET))))
        packs = pack(subs, target)
        groups.extend(packs)
        notes.append("「%s」%d 汉字 ≥ %d → **按子节切成 %d 页**（每页 %d~%d 汉字）"
                     % (title[:14], chars, HEAVY, len(packs), PAGE_TARGET,
                        max(sum(x[1] for x in p) for p in packs)))

    if light:
        lsum = sum(c for _, c in light)
        lavg = lsum / float(len(light))
        if lavg < AVG_PAIR:
            packs = [light[i:i + 2] for i in range(0, len(light), 2)]
            if len(light) == 1:
                notes.append("其余 1 节 %d 汉字（薄节）→ **并入相邻页或单独收尾**" % light[0][1])
            else:
                notes.append("其余 %d 节平均 %.0f 汉字 < %d → **两节并一页**（→ %d 页）"
                             % (len(light), lavg, AVG_PAIR, len(packs)))
        else:
            packs = [[s] for s in light]
            notes.append("其余 %d 节平均 %.0f 汉字 ≥ %d → 一节一页" % (len(light), lavg, AVG_PAIR))
        groups.extend(packs)

    content = len(groups)
    cards = 1 + content
    lo, hi = LO, HI
    if total < SHORT:
        lo, hi = 4, 5
        cards = min(max(cards, lo), hi)
        notes.append("全篇 %d 汉字 < %d → **压到 %d~%d 张**（公式给 %d，取区间内）"
                     % (total, SHORT, lo, hi, 1 + content))
    over = cards > hi
    cards = min(cards, 12)

    return {
        "total_cjk": total,
        "sections": secs,
        "heavy": [s[0] for s in heavy],
        "content_pages": content,
        "suggest_cards": cards,
        "range": [lo, hi],
        "notes": notes,
        "groups": groups,
        "over_band": over,
    }


def main():
    ap = argparse.ArgumentParser(description="页数规划：脚本给答案")
    ap.add_argument("article")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--check", metavar="SPEC.json",
                    help="和一份已写好的规格对账：张数差几张、差在哪")
    args = ap.parse_args()

    p = plan(io.open(args.article, encoding="utf-8").read())

    if args.check:
        raw = io.open(args.check, encoding="utf-8").read()
        spec = json.loads(raw) if args.check.lower().endswith(".json") else __import__("yaml").safe_load(raw)
        n = len(spec.get("cards") or [])
        want = p["suggest_cards"]
        print("对账：plan.py 建议 %d 张（区间 %d~%d）／这份规格 %d 张 → %s"
              % (want, p["range"][0], p["range"][1], n,
                 "一致 ✓" if n == want else "相差 %+d" % (n - want)))
        if n != want:
            print("  建议的页骨架（照它写，不用自己再算）：")
            for i, g in enumerate(p["groups"], 2):
                print("    card-%02d  %s" % (i, " + ".join(t for t, _ in g)[:52]))
            note = ((spec.get("meta") or {}).get("plan_note") or "").strip()
            print("  %s" % ("偏离理由已记录在 meta.plan_note：%s" % note if note
                            else "⚠ 没有记录偏离理由 —— 请在 spec.meta.plan_note 里写明，"
                                 "并同步写进交付报告（门禁不会替你解释）"))
        return 0
    if args.json:
        print(json.dumps(p, ensure_ascii=False, indent=1))
        return 0

    print("文章：%s" % args.article)
    print("规模：%d 汉字 / 二级节 %d 个" % (p["total_cjk"], len(p["sections"])))
    print("")
    print("每节规模：")
    for t, c in p["sections"]:
        flag = "（薄节）" if c < THIN else ("（重章节 → 按子节切）" if c >= HEAVY else "")
        print("  %5d 汉字  %s%s" % (c, t, flag))
    print("")
    print("判定：")
    for n in p["notes"]:
        print("  · %s" % n)
    print("")
    print("→ **建议 %d 张**（区间 %d~%d）" % (p["suggest_cards"], p["range"][0], p["range"][1]))
    if p["over_band"]:
        print("  ⚠ 已超过区间上沿 %d：要么合并相邻页，要么承认这是"
              "「拆系列」的信号（每篇 6~8 张）" % p["range"][1])
    print("")
    print("页骨架（第 1 页固定是 cover 封面）——**照这个分组写，不用自己再算**：")
    print("  card-01  cover")
    for i, g in enumerate(p["groups"], 2):
        titles = " + ".join(t for t, _ in g)
        chars = sum(c for _, c in g)
        print("  card-%02d  %s（%d 汉字）" % (i, titles[:48], chars))
    print("")
    print("版式自己挑（见 [docs/layouts.md] 的对照表）；主题数就是上面的分组数。")
    return 0


if __name__ == "__main__":
    sys.exit(main())