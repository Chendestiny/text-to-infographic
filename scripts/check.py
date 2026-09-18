# -*- coding: utf-8 -*-
"""check.py —— 一条命令跑完全部门禁，输出一份统一结论。

为什么要有它（实测数据）：一轮 hermes 生图跑到 **28 次 terminal 调用、4 轮返工** ——
每条门各跑一次（plan / preflight / validate / pipeline），agent 还要自己把几份输出拼起来判断。
这里合成**一次调用**，并把"必须改的"和"只是提示"分开列。

用法
    python scripts/check.py <spec.json>                      # 预检 + 规格门 + 像素门
    python scripts/check.py <spec.json> --article <文章.md>   # 额外做页数对账
    python scripts/check.py <spec.json> --no-render          # 只过门，不出图
    python scripts/check.py <spec.json> --budget             # 顺带打印每槽字数预算表

退出码：0 = 可以交付；1 = 有硬问题（看输出里的 ✗）
"""
import argparse
import io
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)


def run(script, *args):
    cmd = [sys.executable, os.path.join(HERE, script)] + [str(a) for a in args]
    env = dict(os.environ)
    env.setdefault("T2I_BACKEND", os.environ.get("T2I_BACKEND", "cdp"))
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, env=env)
    return (p.stdout or "") + (p.stderr or ""), p.returncode


def main():
    ap = argparse.ArgumentParser(description="一条命令跑完全部门禁")
    ap.add_argument("spec")
    ap.add_argument("--article", help="给了就做页数对账（plan.py --check）")
    ap.add_argument("--out", help="出图目录（默认 spec 所在目录）")
    ap.add_argument("--no-render", action="store_true")
    ap.add_argument("--budget", action="store_true", help="打印每槽字数预算表")
    a = ap.parse_args()

    spec_path = os.path.abspath(a.spec)
    out = a.out or os.path.dirname(spec_path)
    hard, soft = [], []

    # ① 文字级预检（0 成本，不需要浏览器）
    o, rc = run("preflight.py", spec_path)
    for l in o.splitlines():
        if l.strip().startswith("✗"):
            hard.append("预检 " + l.strip())
        elif re.search(r"文字级预检", l):
            print(l.strip())

    # ② 页数对账（只有给了文章才做）
    if a.article:
        o, rc = run("plan.py", a.article, "--check", spec_path)
        for l in o.splitlines():
            if "对账" in l or "⚠" in l:
                print(("  " if "⚠" not in l else "✗ ") + l.strip())
                if "⚠" in l:
                    soft.append("页数偏离没写理由")
            elif "plan_note" in l:
                print("  " + l.strip())

    # ②b 规格自带的计划（meta.plan）：不依赖 --article
    try:
        m = (json.load(io.open(spec_path, encoding="utf-8")).get("meta") or {}).get("plan") or {}
        if m.get("suggest"):
            n = len(json.load(io.open(spec_path, encoding="utf-8"))["cards"])
            print("  计划：脚本建议 %s 张（区间 %s~%s）／这份 %d 张%s"
                  % (m["suggest"], (m.get("range") or ["?", "?"])[0],
                     (m.get("range") or ["?", "?"])[1], n,
                     "（理由：%s）" % m["note"][:60] if m.get("note") else "（未写理由）"))
    except (ValueError, KeyError):
        pass

    # ③ 规格门（结构 + 几何硬墙）
    o, rc = run("validate.py", spec_path)
    if rc != 0:
        for l in o.splitlines():
            # 只收**具体条目**，别把段标题（"页数提示（1 处）："）也收进"必须改"
            if l.strip().endswith("：") or re.match(r"^\s*(契约违规|软约束|密集档提示|超过建议字数|页数提示)",
                                                   l):
                continue
            if re.search(r"几何上放不下|未知字段|不渲染|条数越界|超过硬上限", l):
                hard.append("规格门 " + l.strip()[:130])
    print([l.strip() for l in o.splitlines() if "契约校验" in l][0] if "契约校验" in o
          else "规格门：见下")

    # ④ 像素门 + 几何布局门（要起浏览器）
    if not a.no_render:
        o, rc = run("pipeline.py", spec_path, "-o", out)
        for l in o.splitlines():
            s = l.strip()
            if re.search(r"measure:|verify:|降级 |crosses-|overlap|needs_llm|耗时|⚠ .*需要 LLM", s):
                print("  " + s)
            if re.search(r"crosses-|overlap|需要 LLM 重写", s):
                hard.append("像素门 " + s[:130])
            if s.startswith("[") and ("缩到" in s or "密集档" in s or "截断" in s):
                soft.append(s)

    # ⑤ 可选：预算表
    if a.budget:
        o, rc = run("capacity.py", spec_path, "--all")
        print("\n  每槽字数预算（放不下才是墙，其余是提示）：")
        for l in o.splitlines():
            if re.search(r"宽 \d|口径：", l):
                print("    " + l.strip())

    print("\n" + "=" * 64)
    if hard:
        print("✗ 必须改（%d 处）：" % len(hard))
        for h in hard[:14]:
            print("   " + h)
    else:
        print("✓ 硬问题 0 处 —— 可以交付")
    if soft:
        print("· 提示（%d 处，可改可不改）：" % len(soft))
        for s in soft[:8]:
            print("   " + s)
    print("=" * 64)
    return 1 if hard else 0


if __name__ == "__main__":
    sys.exit(main())