# -*- coding: utf-8 -*-
"""生成「主题风格图鉴」：每套皮肤渲染同一组样张，方便一眼挑。

    python make_theme_gallery.py                     # 全部皮肤 → 桌面 t2i-themes/
    python make_theme_gallery.py --family paper      # 只出纸张族（第 1 类）
    python make_theme_gallery.py --themes crayon,grid
    python make_theme_gallery.py --list              # 只列主题，不出图
    python make_theme_gallery.py -o out/themes --sheet-out docs/images/themes/皮肤图鉴.png

为什么样张是**固定的一套内容**：只有内容一样，差异才全部来自皮肤。
换文案再看就等于同时改了内容和风格，挑不出所以然。
封面也必须和其余样张**讲同一件事** —— 封面写着 A 题、后七张讲 B 题，
放在拼版里一眼就看出来是拼凑的（这条是被用户点出来的）。

产出：
    <out>/00-总览.png                 全部皮肤的封面并排
    <out>/NN-<key>-<中文名>/           每套皮肤一个目录
        card-01-cover_title.png …     同一组 8 张样张
        拼版.jpg                       8 张拼一张（一次看完，比逐张翻快）
    <out>/README.txt                  怎么看、挑完怎么用
    --sheet-out 指定时额外出一张**跨皮肤**对比表（行 = 皮肤，列 = 版式，给 README 用）
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
from render import find_browser, shoot, file_url   # noqa: E402

FONT = os.path.join(HERE, "assets", "fonts", "ZCOOLKuaiLe-Regular.ttf")
BUILD = os.path.join(HERE, "theme-build")

# 跨皮肤对比表用哪几张（行 = 皮肤，列 = 这三张）
CROSS = [0, 2, 5]          # cover_title / chain / bullets 在 SAMPLES 里的下标
# 单皮肤横条（README「出图效果」用）：封面 / 步骤链 / 左右对照 / 四象限
STRIP = [0, 2, 3, 6]
# README 头部横幅：同皮肤但换另外四种版式，避免和上面那条横条重复同一批图
BANNER = [1, 4, 5, 7]      # cover / flow / bullets / pyramid

# ── 样张内容：8 张，覆盖封面 / 结构 / 对照 / 清单 / 图表五大类 ────────────────
# ★ 整套样张讲**同一件事**（Agent 工程），封面和正文才对得上。
SAMPLES = [
    ({"layout": "cover_title",
      "title": "Agent 看着玄\n其实就四件事\n循环 · 工具\n记忆 · 选型",
      "kicker": "AI Agent 工程笔记", "subtitle": "循环 / 工具 / 记忆 / 选型",
      "accent": 2, "note": "看完能上手"},
     "cover_title", "大字标题封面"),

    ({"layout": "cover", "title": "Agent + ReAct 循环",
      "subtitle": "一张图看懂三者的分工",
      "note": "固定流程用 Workflow，自主决策才上 Agent",
      "quads": [
          {"label": "ReAct 循环", "mini": "steps",
           "items": [{"text": "思考"}, {"text": "行动"}, {"text": "观察"}]},
          {"label": "分层协作", "mini": "nested",
           "items": [{"text": "决策层", "desc": "谁来做判断"},
                     {"text": "执行层", "desc": "谁来动手"}],
           "chips": ["感知", "决策", "执行"]},
          {"label": "核心特点", "mini": "list",
           "items": [{"text": "会自己拆步骤"}, {"text": "会调用工具"},
                     {"text": "能记住上下文"}]},
          {"label": "速记总结", "mini": "boxes",
           "items": [{"text": "固定流程"}, {"text": "部分决策"}, {"text": "自主任务"}],
           "line": "越往右越需要 Agent"}]},
     "cover", "四宫格封面"),

    ({"layout": "chain", "title": "Function Calling",
      "subtitle": "[[tool_call]] 是模型吐的，干活的是代码",
      "steps": [{"text": "① 注入 [[tools 定义]]"},
                {"text": "② 模型返回 tool_calls", "fill": "yellow"},
                {"text": "③ 你的代码执行", "fill": "blue"},
                {"text": "④ 结果 [[塞回历史]]"}],
      "note": "回到 ② 步，直到模型不再调工具",
      "dashed": True, "dashed_label": "一次调用的完整回路"},
     "chain", "步骤链"),

    ({"layout": "compare", "title": "长任务别恋战一个窗口",
      "subtitle": "压缩的天花板摆在那，[[所以换路线]]",
      "left": {"label": "老路线：窗口内压缩",
               "blocks": ["到阈值就摘要", "细节逐代丢失", "长任务越跑越不准"],
               "note": "官方仓库就躺着这类 issue"},
      "right": {"label": "新路线：外置 + 硬切",
                "blocks": ["任务分段", "每段一个干净窗口",
                           {"text": "结论写进外部文件", "fill": "yellow"}],
                "note": "窗口是工作台，不是仓库"}},
     "compare", "左右对照"),

    ({"layout": "flow", "title": "记忆：跨了会话不失忆",
      "subtitle": "短期是窗口，长期是[[带索引的持久库]]",
      "nodes": [{"text": "短期记忆"}, {"text": "显式纠正", "fill": "yellow"},
                {"text": "长期库"}, {"text": "按需取回"}],
      "note": "每轮自动提炼偏好，两周下来全是噪声",
      "note2": "只在用户显式纠正或确认时才写",
      "bottom": [{"text": "落库", "desc": "写业务表"},
                 {"text": "回显", "desc": "面板按会话"},
                 {"text": "索引", "desc": "小而不胀"}],
      "dashed": True, "dashed_label": "MCP：首尾那套传输"},
     "flow", "横向链路"),

    ({"layout": "bullets", "title": "主动砍 token 的三刀",
      "subtitle": "token 就是钱，[[每一行都按 token 计价]]",
      "items": [
          {"no": "①", "head": "砍工具原文保结论", "desc": "结果先消化成一句话，再进窗口。"},
          {"no": "②", "head": "砍历史保摘要", "desc": "十轮对话压成五行要点。"},
          {"no": "③", "head": "检索结果标来源", "desc": "标明出处和适用范围，模型才知道信多少。"}]},
     "bullets", "清单"),

    ({"layout": "matrix", "title": "向量库按规模挑",
      "subtitle": "先用最简单的跑通，[[真撞到瓶颈再换]]",
      "labels": {"top": "数据量从小到大"},
      "cells": [
          {"head": "十万级", "desc": "chroma 本地玩具"},
          {"head": "百万千万", "desc": "pgvector / Qdrant"},
          {"head": "十亿级", "desc": "Pinecone 全托管"},
          {"head": "百亿级", "desc": "Milvus 分布式"}]},
     "matrix", "四象限"),

    ({"layout": "pyramid", "title": "Agent 能力金字塔",
      "subtitle": "越往上越需要[[自主决策]]",
      "note": "底座不稳，上层就是幻觉",
      "levels": [
          {"text": "自主规划", "desc": "自己决定做什么"},
          {"text": "工具编排", "desc": "串多个工具"},
          {"text": "单工具调用"},
          {"text": "提示词工程"},
          {"text": "基础模型能力"}]},
     "pyramid", "金字塔"),
]


def _desktop():
    for d in ("Desktop", "桌面"):
        p = os.path.join(os.path.expanduser("~"), d)
        if os.path.isdir(p):
            return p
    return os.path.expanduser("~")


def _label_font(size):
    return sheet.label_font(size)


def main():
    ap = argparse.ArgumentParser(description="主题风格图鉴：每套皮肤渲染同一组样张")
    ap.add_argument("-o", "--out", default=os.path.join(_desktop(), "t2i-themes"),
                    help="输出目录（默认桌面 t2i-themes/）")
    ap.add_argument("--themes", default="", help="只出这几套（逗号分隔）")
    ap.add_argument("--family", default="", choices=["", "paper", "diagram"],
                    help="按族筛：paper = 第 1 类（复用版式）/ diagram = 第 2 类（工程风）")
    ap.add_argument("--sheet-out", default="",
                    help="额外出一张**跨皮肤对比表**（行=皮肤，列=封面/步骤链/清单），给 README 用")
    ap.add_argument("--strips-out", default="",
                    help="额外给**每套皮肤**出一条 4 图横条（README 的「出图效果」用）")
    ap.add_argument("--strip-thumb", type=int, default=380, help="横条单格宽度（默认 380）")
    ap.add_argument("--banner-out", default="",
                    help="额外出一张**头部横幅**（只出 --banner-theme 那一套，用另外四种版式）")
    ap.add_argument("--banner-theme", default="crayon", help="横幅用哪套皮肤（默认 crayon）")
    ap.add_argument("--banner-thumb", type=int, default=420, help="横幅单格宽度（默认 420）")
    ap.add_argument("--scale", type=int, default=1, help="出图倍率，1=1080×1440（默认）")
    ap.add_argument("--list", action="store_true", help="只列出主题")
    a = ap.parse_args()

    if a.list:
        for k, label, en, desc in theme.catalog():
            print("  %-10s %-5s %-6s %-6s %s"
                  % (k, theme.get(k)["family"], en, label, desc))
        return 0

    keys = [s.strip() for s in a.themes.split(",") if s.strip()] or theme.names()
    for k in keys:
        if k not in theme.THEMES:
            sys.exit("未知主题 %r（可用：%s）" % (k, ", ".join(theme.names())))
    if a.family:
        keys = [k for k in keys if theme.get(k)["family"] == a.family]
        if not keys:
            sys.exit("--family %s 一套皮肤都没筛出来" % a.family)

    out = os.path.abspath(a.out)
    os.makedirs(out, exist_ok=True)
    os.makedirs(BUILD, exist_ok=True)
    browser = find_browser()
    print("浏览器：%s" % browser)
    print("输出：%s\n" % out)

    covers, cross, failed = [], [], []
    for n, key in enumerate(keys, 1):
        T = theme.THEMES[key]
        sub = os.path.join(out, "%02d-%s-%s" % (n, key, T["label"]))
        os.makedirs(sub, exist_ok=True)
        # ★ 一次换皮肤，整组样张都跟着它 —— 逐张渲染时 ink 的主题是模块全局，
        #   所以这里必须每套皮肤重新 use_theme 一次（render_card 内部也会再设一次）
        ink.use_theme(key)
        pngs, labels = [], []
        for i, (card, layout, cn) in enumerate(SAMPLES, 1):
            html = ink.render_card(card, i - 1, len(SAMPLES), {"theme": key}, file_url(FONT))
            hp = os.path.join(BUILD, "%s-%02d.html" % (key, i))
            with io.open(hp, "w", encoding="utf-8") as f:
                f.write(html)
            png = os.path.join(sub, "card-%02d-%s.png" % (i, layout))
            ok, msg = shoot(browser, hp, png, 1080, 1440, a.scale)
            print("  %-10s %-26s %s" % (key, os.path.basename(png), msg))
            if ok:
                pngs.append(png)
                labels.append("%02d  %s · %s" % (i, layout, cn))
                if i == 1:
                    covers.append((key, T, png))
                if (i - 1) in CROSS:
                    cross.append((png, "%s · %s · %s" % (T["label"], layout, cn)))
            else:
                failed.append(png)
        if pngs:
            sheet.contact_sheet(pngs, os.path.join(sub, "拼版.jpg"), cols=4, thumb_w=420,
                                title="%s · %s" % (T["label"], key),
                                note=T["desc"], labels=labels)
        if a.strips_out and pngs:
            # 单皮肤横条：一屏之内把"这套皮肤长什么样"讲完，四种版式并排
            so = os.path.abspath(a.strips_out)
            os.makedirs(so, exist_ok=True)
            idx = [i for i in STRIP if i < len(pngs)]
            sheet.contact_sheet(
                [pngs[i] for i in idx], os.path.join(so, "%02d-%s.png" % (n, key)),
                cols=len(idx), thumb_w=a.strip_thumb,
                title="%s · %s" % (T["label"], key), note=T["desc"],
                labels=["%s · %s" % (SAMPLES[i][1], SAMPLES[i][2]) for i in idx])
        if a.banner_out and pngs and key == a.banner_theme:
            # README 头部那张横幅：用**另外四种版式**，免得和下面那条横条一模一样
            bo = pngs and os.path.abspath(a.banner_out)
            os.makedirs(os.path.dirname(bo), exist_ok=True)
            idx = [i for i in BANNER if i < len(pngs)]
            sheet.contact_sheet(
                [pngs[i] for i in idx], bo, cols=len(idx), thumb_w=a.banner_thumb,
                title="%s · %s" % (T["label"], key), note=T["desc"],
                labels=["%s · %s" % (SAMPLES[i][1], SAMPLES[i][2]) for i in idx])
            print("\n横幅：%s" % bo)

    # 总览：每套皮肤的封面并排，一眼看完全部候选
    if covers:
        sheet.contact_sheet([p for _k, _T, p in covers],
                            os.path.join(out, "00-总览.png"), cols=3, thumb_w=430,
                            title="text-to-infographic · 主题总览（%d 套皮肤）" % len(covers),
                            note="同一份内容，只换皮肤",
                            labels=["%s  %s" % (T["label"], k) for k, T, _p in covers])

    # 跨皮肤对比表：行 = 皮肤，列 = 封面/步骤链/清单（README 只用这一张）
    if a.sheet_out and cross:
        cols = len(CROSS)
        sheet.contact_sheet([p for p, _l in cross], os.path.abspath(a.sheet_out),
                            cols=cols, thumb_w=430,
                            title="text-to-infographic · 皮肤图鉴（%d 套）" % len(keys),
                            note="同一份内容，只换 meta.theme",
                            labels=[l for _p, l in cross])
        print("\n对比表：%s" % os.path.abspath(a.sheet_out))

    # 挑完怎么用，写下来，省得回头问
    with io.open(os.path.join(out, "README.txt"), "w", encoding="utf-8") as f:
        f.write("text-to-infographic 主题图鉴\n"
                "================================\n\n"
                "先看 00-总览.png（每套皮肤的同款封面并排），\n"
                "再进感兴趣的那套目录看 拼版.jpg（8 张样张一次看完）。\n\n"
                "看上哪套，在规格里写一行就够了：\n\n"
                "  \"meta\": { \"theme\": \"crayon\" }\n\n"
                "可用主题（key 就是 meta.theme 的值）：\n")
        for k, label, en, desc in theme.catalog():
            f.write("  %-10s %-8s %-6s %-6s %s\n"
                    % (k, theme.get(k)["family"], en, label, desc))
        f.write("\n分组：paper = 复用现有版式（纸张族）；diagram = 工程风（节点重画过）。\n"
                "默认是 crayon（蜡笔纸感）。不写 meta.theme 就是它。\n"
                "主题只换皮，不改版式字段、字数与四道门口径。\n")

    print("\n%d 套皮肤 × %d 张样张 → %s" % (len(keys), len(SAMPLES), out))
    if failed:
        print("失败 %d 张：%s" % (len(failed), ", ".join(os.path.basename(p) for p in failed)))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
