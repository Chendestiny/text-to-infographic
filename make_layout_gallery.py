# -*- coding: utf-8 -*-
"""生成「版式方案图鉴」：每种版式渲染一张真实样张，方便挑选与回归比对。

    python make_layout_gallery.py                # 输出到 gallery-out/
    python make_layout_gallery.py -o <dir>       # 指定输出目录
"""
import argparse
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "scripts"))
import ink  # noqa: E402
from render import find_browser, shoot, file_url  # noqa: E402

FONT = os.path.join(HERE, "assets", "fonts", "ZCOOLKuaiLe-Regular.ttf")
BUILD = os.path.join(HERE, "gallery-build")

GALLERY = [
    ({"layout": "cover", "title": "Agent + ReAct 循环 + Workflow",
      "subtitle": "一张图看懂三者的分工与边界",
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

    ({"layout": "hub", "title": "Agent 的手和脚",
      "subtitle": "工具 · MCP 与 Skills", "hub": "Agent",
      "note": "一篇讲清 Agent 的手脚三件套",
      "items": [
          {"big": "手", "en": "Function Calling", "tag": "能调", "color": "blue"},
          {"big": "脚", "en": "MCP", "tag": "能接", "color": "yellow"},
          {"big": "技能", "en": "Agent Skills", "tag": "会挑着递", "color": "pink"}]},
     "hub", "中心圆"),

    ({"layout": "chain", "title": "Function Calling",
      "subtitle": "[[tool_call]] 是模型吐的，干活的是代码",
      "steps": [{"text": "① 注入 [[tools 定义]]"},
                {"text": "② 模型返回 tool_calls", "fill": "yellow"},
                {"text": "③ 你的代码执行", "fill": "blue"},
                {"text": "④ 结果 [[塞回历史]]"}],
      "note": "回到 ② 步，直到模型不再调工具",
      "dashed": True, "dashed_label": "一次调用的完整回路"},
     "chain", "步骤链"),

    ({"layout": "cycle", "title": "ReAct 循环：Agent 的心脏",
      "subtitle": "思考 → 动手 → 看结果，转一圈出一个结论",
      "keywords": ["Thought", "Action", "Observation", "答案"],
      "nodes": [
          {"text": "Thought", "desc": "模型想下一步要干啥"},
          {"text": "Action", "desc": "调工具 / 查知识库"},
          {"text": "Observation", "desc": "拿到结果再思考"},
          {"text": "答案", "desc": "不再调工具才输出"}]},
     "cycle", "环形循环"),

    ({"layout": "spectrum", "title": "Workflow vs Agent:\n什么时候该上谁？",
      "subtitle": "光谱三档，别硬上 Agent",
      "stages": ["固定流程", "部分决策", "复杂自主任务"],
      "ends": ["Workflow", "Agent"],
      "items": [
          {"text": "[[固定流程]]：直接用 Workflow"},
          {"text": "部分决策用 [[LLM]] + [[流程]]"},
          {"text": "复杂[[自主任务]]才上 [[Agent]]"},
          {"text": "别为了用 [[Agent]] 而用"}],
      "note": "按任务的自主程度选，不按潮流选"},
     "spectrum", "光谱决策"),

    ({"layout": "timeline", "title": "知识库上线五步",
      "subtitle": "嵌入是独立一步，[[重跑成本可控]]",
      "steps": [
          {"text": "加载", "desc": "Markdown / HTML"},
          {"text": "清洗", "desc": "去页眉页脚"},
          {"text": "切片", "desc": "带标题切"},
          {"text": "嵌入", "desc": "批量打完"},
          {"text": "落库", "desc": "metadata 齐全"}],
      "note": "每步独立可重跑，坏了只重跑那一步"},
     "timeline", "时间轴"),

    ({"layout": "flow", "title": "记忆：跨了会话不失忆",
      "subtitle": "短期是窗口，长期是[[带索引的持久库]]",
      "nodes": [{"text": "短期记忆"}, {"text": "显式纠正", "fill": "yellow"},
                {"text": "长期库"}, {"text": "按需取回"}],
      "note": "每轮自动提炼偏好，两周下来全是噪声",
      "note2": "只在用户显式纠正或确认时才写",
      "bottom": [
          {"text": "落库", "desc": "写业务表"},
          {"text": "回显", "desc": "面板按会话"},
          {"text": "索引", "desc": "小而不胀"}],
      "dashed": True, "dashed_label": "MCP：首尾那套传输"},
     "flow", "横向链路"),

    ({"layout": "compare", "title": "长任务别恋战一个窗口",
      "subtitle": "压缩的天花板摆在那，[[所以换路线]]",
      "left": {"label": "老路线：窗口内压缩",
               "blocks": ["到阈值就摘要", "细节逐代丢失", "长任务越跑越不准"],
               "note": "Codex 官方仓库就躺着这类 issue"},
      "right": {"label": "新路线：外置 + 硬切",
                "blocks": ["任务分段", "每段一个干净窗口",
                           {"text": "结论写进外部文件", "fill": "yellow"}],
                "note": "窗口是工作台，不是仓库"}},
     "compare", "左右对照"),

    ({"layout": "bullets", "title": "主动砍 token 的三刀",
      "subtitle": "token 就是钱，[[窗口里每一行都按 token 计价]]",
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

    ({"layout": "arch", "title": "脚：MCP",
      "subtitle": "[[Model Context Protocol]]",
      "host_label": "Host 跑 Agent",
      "inner": [{"text": "Client", "desc": "一对一握手", "fill": "yellow"},
                {"text": "Client", "desc": "另一个 Server"}],
      "link_label": "标准协议",
      "server": "Server", "server_desc": "暴露工具 / 资源", "server_fill": "pink",
      "line": "给工具调用定标准，像 [[USB-C]]：插哪都行",
      "chips": [{"text": "Host", "desc": "跑 Agent"},
                {"text": "Client", "desc": "负责握手"},
                {"text": "Server", "desc": "暴露工具"}],
      "note": "记这三个角色就够了"},
     "arch", "结构图"),
]

CN = {"cover": "封面", "chain": "步骤链", "cycle": "环形循环", "spectrum": "光谱决策",
      "timeline": "时间轴", "flow": "横向链路", "compare": "左右对照",
      "bullets": "清单", "matrix": "四象限", "arch": "结构图", "raw": "自定义"}


def main():
    ap = argparse.ArgumentParser(description="渲染全部版式的方案样张（图鉴）")
    ap.add_argument("-o", "--out", default=os.path.join(HERE, "gallery-out"),
                    help="样张输出目录，默认 gallery-out/")
    args = ap.parse_args()
    out_dir = os.path.abspath(args.out)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    if not os.path.isdir(BUILD):
        os.makedirs(BUILD)

    browser = find_browser()
    print("浏览器：%s\n" % browser)
    failed = []
    for i, (card, layout, cn) in enumerate(GALLERY):
        html = ink.render_card(card, i, len(GALLERY), {"frame": ["card"]},
                               file_url(FONT))
        hp = os.path.join(BUILD, "g-%02d.html" % (i + 1))
        with io.open(hp, "w", encoding="utf-8") as f:
            f.write(html)
        png = os.path.join(out_dir, "方案-%02d-%s-%s.png" % (i + 1, layout, cn))
        ok, msg = shoot(browser, hp, png, 1080, 1440, 2)
        print("  %-36s %s" % (os.path.basename(png), msg))
        if not ok:
            failed.append(png)
    if failed:
        print("\n失败 %d 张" % len(failed))
        return 1
    print("\n%d 个方案 → %s" % (len(GALLERY), out_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
