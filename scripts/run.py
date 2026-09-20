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


def run(script, *args):
    env = dict(os.environ)
    env.setdefault("T2I_BACKEND", os.environ.get("T2I_BACKEND", "cdp"))
    p = subprocess.run([sys.executable, os.path.join(HERE, script)] + [str(a) for a in args],
                       capture_output=True, text=True, encoding="utf-8", errors="replace",
                       cwd=ROOT, env=env)
    return (p.stdout or "") + (p.stderr or ""), p.returncode


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
    a = ap.parse_args()

    if a.plan:                      # 规划模式：一条命令入口收敛到 run.py
        o, _ = run("plan.py", a.plan)
        print(o.rstrip())
        return 0
    if not a.spec:
        print("用法：run.py <spec.json> [--article 文章.md] [--out 目录] | run.py --plan 文章.md")
        return 2
    spec = os.path.abspath(a.spec)
    out = a.out or os.path.dirname(spec)
    hard, soft = [], []

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
        o, rc_pipe = run("pipeline.py", spec, "-o", out)
        pipe_out = o                      # ★ 后面 o 会被 review_sheet 覆盖，先存一份
        # ★ pipeline 崩了必须算硬问题：原来只扫输出里的关键词，脚本抛异常时既没有
        #   measure: 也没有 needs_llm，于是"硬问题 0 处"是**假绿**（实测踩过：
        #   ink.py 被裁坏、palette 未定义，run.py 还报可以交付）
        if rc_pipe != 0 and "measure:" not in o:
            hard.append("像素门｜pipeline 异常退出（exit=%d）：%s"
                        % (rc_pipe, (o.strip().splitlines() or [""])[-1][:110]))
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