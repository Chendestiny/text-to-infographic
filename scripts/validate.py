# -*- coding: utf-8 -*-
"""validate.py —— 字数契约校验（编排流的规格门，纯脚本零 LLM）

在 build 之前跑：LLM 填完规格先过这道门，超契约就报**精确路径**，
Agent 拿着报错一次改对。这道门拦住 90% 的问题，后面 measure 的像素门
只兜字体度量估算不准的那一小部分。

用法
    python scripts/validate.py examples/agent-roadmap.yaml        # 校验+列出违规
    python scripts/validate.py cards.yaml --quiet                  # 只看退出码
    python scripts/validate.py cards.yaml --fix-hint               # 附修改建议

有效字数口径：汉字 = 1，其他 = 0.5。规格里的 [[高亮]] 标记不计。
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
# 参考值来自小红书配图规范：官方上限 1–18 张，推荐 6–9 张。
# 没有这道闸时 Agent 会一路"每个小节一页"切下去——实测一篇 228 行、5 章 9 个坑的文章
# 被切成 11 张，按章节合并只要 7 张。
PLATFORM_MAX = 18          # 平台硬上限：单篇超过 18 张发不出去
SWEET_MIN, SWEET_MAX = 6, 9  # 推荐区间（封面 + 5~8 内容页）
SERIES_HINT = 13           # 到这儿就该拆成系列，而不是继续加页


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


def validate(spec, layouts):
    """layouts = templates/contracts.yaml 里的 layouts 字典。返回 (errors, warnings)。"""
    issues, warnings = [], []
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
    elif n < 4:
        warnings.append(("cards", "共 %d 页偏少：要么切太粗，要么文章本来就短" % n, ""))
    for i, card in enumerate(cards):
        layout = card.get("layout")
        if layout not in layouts:
            issues.append(("card-%02d" % (i + 1), "未知版式 %r" % layout, ""))
            continue
        cid = "card-%02d(%s)" % (i + 1, layout)
        _walk(card, layouts[layout], cid, issues, warnings)
    return issues, warnings


def main():
    ap = argparse.ArgumentParser(description="字数契约校验（规格门）")
    ap.add_argument("spec")
    ap.add_argument("--contracts", default=CONTRACTS)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()
    try:
        import yaml
    except ImportError:
        raise SystemExit("读 YAML 需要 pyyaml")
    spec = yaml.safe_load(io.open(args.spec, encoding="utf-8").read())
    contracts = yaml.safe_load(io.open(args.contracts, encoding="utf-8").read())
    errors, warns = validate(spec, contracts.get("layouts") or {})
    # 页数提示和"文案太长"是两类问题，混在一个标题下会误导 Agent
    page_warns = [w for w in warns if w[0] == "cards"]
    text_warns = [w for w in warns if w[0] != "cards"]
    if page_warns:
        print("页数提示（%d 处）：" % len(page_warns))
        for path, msg, sample in page_warns:
            print("  %-42s %s" % (path, msg))
    if text_warns:
        print("软约束（会自动换行/缩字，建议改短）%d 处：" % len(text_warns))
        for path, msg, sample in text_warns:
            print("  %-42s %s  %s" % (path, msg, sample))
    if errors:
        print("\n契约违规（硬约束，必然溢出）%d 处：" % len(errors))
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
