# -*- coding: utf-8 -*-
"""validate.py —— 字数契约校验（编排流的规格门，纯脚本零 LLM）

在 build 之前跑：LLM 填完规格先过这道门，超契约就报**精确路径**，
Agent 拿着报错一次改对。这道门拦住 90% 的问题，后面 measure 的像素门
只兜字体度量估算不准的那一小部分。

用法
    python scripts/validate.py examples/agent-roadmap.yaml        # 校验+列出违规
    python scripts/validate.py cards.yaml --quiet                 # 只看退出码
    python scripts/validate.py cards.yaml --fix-hint              # 附修改建议
    python scripts/validate.py --count "一段中文 copy" "another"   # 只算有效字数

有效字数口径：汉字 = 1，其他 = 0.5（含全角标点与空格、换行）；规格里的 [[高亮]] 标记不计。
"""
import argparse
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONTRACTS = os.path.join(ROOT, "templates", "contracts.yaml")

HL_RE = re.compile(r"\[\[(.+?)(?:\|([a-z]{1,2}))?\]\]")

# ---------------------------------------------------------------- 页数纪律
# 这是**产品约束**，不是技术约束：渲染只要 0.5 秒/页，100 页也不会卡机器；
# 真正的代价是 Agent 写文案 + 复核的时间，以及读者划不完的完读率。
# 参考值来自小红书配图规范：官方上限 1–18 张，推荐 6–9 张（短帖 4~5 张也正常）。
# 没有这道闸时 Agent 会一路"每个小节一页"切下去——实测一篇 228 行、5 章 9 个坑的文章
# 被切成 11 张，按章节合并只要 7 张。
PLATFORM_MAX = 18          # 平台硬上限：单篇超过 18 张发不出去
SWEET_MIN, SWEET_MAX = 4, 9  # 推荐区间（封面 + 3~8 内容页）；6~9 是平台偏好区
SERIES_HINT = 13           # 到这儿就该拆成系列，而不是继续加页

# ---------------------------------------------------------------- 未知字段
# 为什么必须有这道检查：规格里写了引擎不认识的字段时，**三道门会一起失明** ——
#   契约只校验它认识的槽位 → 不报；渲染器没有该字段的分支 → 不画也不登记；
#   内容门只比对"渲染器登记过的文字" → 无从比对。结果是三道全绿、内容已在图上消失。
# 真实事故：5 份示例的序号字段全写成 "false"（YAML 1.1 把裸 no 当布尔假，dump 成 JSON
# 就成了 "false"），① ② ③ 从来没渲染出来过，没有任何一道门报警。
NOTE_LAYOUTS = {"arch", "chain", "cover", "flow", "hub", "matrix", "pyramid",
                "spectrum", "timeline"}      # 真的读 card["note"] 的版式（扫 ink.py 实测）
ENGINE_KEYS = {"layout", "frame", "dashed", "dashed_label", "svg", "fs", "fs2",
               "gradient", "color", "fill", "no", "mini", "line", "chips",
               "text", "desc", "big", "en", "tag", "head", "each"}


def eff_len(text):
    """有效字数：汉字 1 + 其他 0.5；高亮标记剥离后计。"""
    s = HL_RE.sub(lambda m: m.group(1), text or "")
    cjk = sum(1 for c in s if ord(c) > 0x2E80)
    return cjk + (len(s) - cjk) * 0.5


def _check_slot(path, value, rule, issues, warnings):
    """按规则校验一个文字槽位。

    rule.soft = True 表示该槽位会自动换行/自动缩字，超限只警告不阻断；
    否则是硬约束（SVG 直排文本，超了必然溢出）。
    """
    v = value or ""
    if isinstance(rule, dict) and "each" in rule:
        if not isinstance(v, list):
            issues.append((path, "应为列表", str(v)[:20]))
            return
        each = rule["each"]
        c = rule.get("count")
        if c is not None:
            lo, hi = (c, c) if isinstance(c, int) else (c.get("min", 0), c.get("max", 99))
            if not (lo <= len(v) <= hi):
                issues.append((path, "条数 %d 超出 %s" % (len(v), c), ""))
        for i, item in enumerate(v):
            _check_slot("%s[%d]" % (path, i), item, each, issues, warnings)
        return
    if isinstance(rule, dict) and "count" in rule and isinstance(v, list):
        c = rule["count"]
        lo, hi = (c, c) if isinstance(c, int) else (c.get("min", 0), c.get("max", 99))
        if not (lo <= len(v) <= hi):
            issues.append((path, "条数 %d 超出 %s" % (len(v), c), ""))
        fields = rule.get("fields") or {}
        for i, item in enumerate(v):
            for fk, fr in fields.items():
                fv = item.get(fk) if isinstance(item, dict) else item
                _check_slot("%s[%d].%s" % (path, i, fk), fv, fr, issues, warnings)
        return
    n = eff_len(v)
    lo = rule.get("min") if isinstance(rule, dict) else None
    hi = rule.get("max") if isinstance(rule, dict) else None
    sink = warnings if rule.get("soft") else issues
    if hi is not None and n > hi:
        sink.append((path, "%.1f > max %s%s" % (n, hi, "（软）" if rule.get("soft") else ""),
                     str(v)[:26]))
    if lo is not None and n < lo:
        sink.append((path, "%.1f < min %s" % (n, lo), str(v)[:26]))


def _walk(node, contract, path, issues, warnings):
    """按契约递归校验规格树。契约键和规格键一一对应。"""
    for key, rule in contract.items():
        p = "%s.%s" % (path, key)
        v = node.get(key)
        if v is None:
            if isinstance(rule, dict) and ("min" in rule or "count" in rule):
                if rule.get("required") or "min" in (rule if isinstance(rule, dict) else {}):
                    issues.append((p, "缺失", ""))
            continue
        if isinstance(rule, dict) and ("fields" in rule or "each" in rule):
            _check_slot(p, v, rule, issues, warnings)
        elif isinstance(v, dict) and isinstance(rule, dict) and not (
                "min" in rule or "max" in rule or "count" in rule):
            _walk(v, rule, p, issues, warnings)  # 嵌套（如 compare.left/right）
        elif isinstance(rule, dict):
            _check_slot(p, v, rule, issues, warnings)


def _contract_keys(node, out):
    """把 contracts.yaml 里出现过的所有字段名收成一个集合（供未知字段检查）。"""
    if isinstance(node, dict):
        for k, v in node.items():
            out.add(k)
            _contract_keys(v, out)
    return out


def _walk_keys(node, allowed, path, sink):
    """递归找规格里引擎不认识的键 —— 这类字段写了不会渲染，也不会有任何报错。"""
    if isinstance(node, dict):
        for k, v in node.items():
            # 白名单：契约里出现过的字段 + 引擎专用字段 + `*_fill` 这类上色字段 + `_` 开头的私有注释
            if isinstance(k, str) and k not in allowed \
                    and not k.endswith("_fill") and not k.startswith("_"):
                sink.append(("%s.%s" % (path, k),
                             "引擎不认识的字段：写了也不会渲染（会不会是拼错了？）", ""))
            _walk_keys(v, allowed, "%s.%s" % (path, k), sink)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk_keys(v, allowed, "%s[%d]" % (path, i), sink)


def validate(spec, layouts):
    """layouts = templates/contracts.yaml 里的 layouts 字典。返回 (errors, warnings)。"""
    issues, warnings, unknown = [], [], []
    cards = spec.get("cards") or []
    n = len(cards)
    # 作者可以在 meta.max_cards 里显式声明这次的预算（长文/教程类），但仍受平台上限约束
    budget = int(((spec.get("meta") or {}).get("max_cards")) or SWEET_MAX)
    budget = min(budget, PLATFORM_MAX)
    if n > PLATFORM_MAX:
        issues.append(("cards", "共 %d 页 > 平台上限 %d：小红书单篇最多 18 张图，多出来的发不出去"
                                "（改法：合并相邻小节，或拆成系列每篇 6~9 张）" % (n, PLATFORM_MAX), ""))
    elif n > budget:
        tail = ("；已经到 %d 张以上，建议拆成系列（每篇 6~9 张），而不是继续加页" % SERIES_HINT
                if n >= SERIES_HINT else
                "；先合并相邻小节，靠版式承载密度（bullets 4~6 条 / chain 5~6 步）")
        warnings.append(("cards", "共 %d 页 > 预算 %d（推荐 %d~%d）%s"
                                  % (n, budget, SWEET_MIN, SWEET_MAX, tail), ""))
    elif n < 3:
        warnings.append(("cards", "共 %d 页偏少：要么切太粗，要么文章本来就短" % n, ""))

    allowed = _contract_keys(layouts, set()) | ENGINE_KEYS
    for i, card in enumerate(cards):
        layout = card.get("layout")
        cid = "card-%02d(%s)" % (i + 1, layout)
        if layout == "raw":
            if not card.get("svg"):
                issues.append((cid, "raw 版式必须给 svg 字段", ""))
            continue
        if layout not in layouts:
            issues.append(("card-%02d" % (i + 1), "未知版式 %r" % layout, ""))
            continue
        if card.get("note") and layout not in NOTE_LAYOUTS:
            issues.append((cid + ".note",
                           "该版式不渲染 note（会被静默丢弃）：改用 %s，或把这段内容并进 items[].desc"
                           % "/".join(sorted(NOTE_LAYOUTS)), ""))
        _walk_keys(card, allowed, cid, unknown)
        _walk(card, layouts[layout], cid, issues, warnings)
    warnings.extend(unknown)
    return issues, warnings


# 不渲染 card["note"] 的版式（文档里也要写清楚，见 docs/layouts.md）
def main():
    ap = argparse.ArgumentParser(description="字数契约校验（规格门）")
    ap.add_argument("spec", nargs="?", help="规格文件（.json / .yaml）")
    ap.add_argument("--contracts", default=CONTRACTS)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--count", nargs="*", metavar="TEXT",
                    help="只算有效字数就退出（汉字 1、其他 0.5、[[高亮]] 标记不计）")
    args = ap.parse_args()

    if args.count is not None:
        for t in (args.count or []):
            print("  %6.1f  %s" % (eff_len(t), t))
        return 0
    if not args.spec:
        ap.error("要么给规格文件，要么用 --count 算字数")

    try:
        import yaml
    except ImportError:
        raise SystemExit("读 YAML 需要 pyyaml")
    raw = io.open(args.spec, encoding="utf-8").read()
    if args.spec.lower().endswith(".json"):
        spec = json.loads(raw)
    else:
        spec = yaml.safe_load(raw)
    contracts = yaml.safe_load(io.open(args.contracts, encoding="utf-8").read())
    errors, warns = validate(spec, contracts.get("layouts") or {})
    # 三类问题混在一个标题下会误导 Agent，分开打
    page_warns = [w for w in warns if w[0] == "cards"]
    note_warns = [w for w in warns if "引擎不认识的字段" in w[1]]
    text_warns = [w for w in warns if w not in page_warns and w not in note_warns]
    if page_warns:
        print("页数提示（%d 处）：" % len(page_warns))
        for path, msg, sample in page_warns:
            print("  %-42s %s" % (path, msg))
    if note_warns:
        print("\n字段提示（%d 处）——这些字段写了不会渲染：" % len(note_warns))
        for path, msg, sample in note_warns:
            print("  %-42s %s" % (path, msg))
    if text_warns:
        print("\n软约束（会自动换行/缩字，建议改短）%d 处：" % len(text_warns))
        for path, msg, sample in text_warns:
            print("  %-42s %s  %s" % (path, msg, sample))
    if errors:
        print("\n契约违规（硬约束，必须改）%d 处：" % len(errors))
        for path, msg, sample in errors:
            print("  %-42s %s  %s" % (path, msg, sample))
        return 1
    if not warns:
        n = len(spec.get("cards") or [])
        zone = ("在推荐区间 %d~%d 内" % (SWEET_MIN, SWEET_MAX)
                if SWEET_MIN <= n <= SWEET_MAX else "（%d 张）" % n)
        print("契约校验通过（%d 页，%s，0 硬 / 0 软）。" % (n, zone))
    return 0


if __name__ == "__main__":
    sys.exit(main())