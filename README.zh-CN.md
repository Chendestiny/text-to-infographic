# text-to-infographic

**把长文/文章转成小红书、Instagram 风格的信息卡片图文——封面 + 每页一个要点，
3:4 竖版手绘卡片风，直接可发。**

[English](README.md)

文字始终清晰不含糊（不像 AI 生图那样糊字），每一页都能手改，排版全流程由工具完成——
你只需要把文章交给它。

![](docs/images/samples/roadmap-cover.png)

## 为什么不让模型直接画？

AI 生图的致命伤是文字必糊，中文尤甚。让 LLM 自由发挥写 HTML「信息图」，每次都不一样：
间距不一致、文字出框、版式一次性。

这个 skill 把 LLM 挪到它擅长的地方（读文章、定结构、压文案），像素全部交给确定性渲染器：

```
文章.md ──> [LLM] cards.json ──> build.py ──> measure（真实浏览器实测）──> PNG × N
              只有这一步需要        所有像素决策都              校验循环
              LLM                  写死在脚本里                （LangGraph 风格）
```

## 快速开始

```bash
git clone https://github.com/Chendestiny/text-to-infographic
cd text-to-infographic
python scripts/doctor.py            # 环境自检
                                    #   Windows 上若 `python` 不在 PATH，改用 `py -3`
python scripts/pipeline.py examples/agent-roadmap.json -o out/
```

- 规格支持 **.json（零第三方依赖）** 或 .yaml（需 `pip install pyyaml`）
- 渲染需要任意 Chromium 系浏览器（Chrome / Edge / Chromium），自动探测
- 字体（站酷快乐体，OFL 许可）已内置，无需安装

面向 Agent 的完整工作流见 [SKILL.md](SKILL.md)；
细节手册（版式字段、字数契约、渲染后端、排障）在 [docs/](docs/)。

## 容量契约系统（核心设计）

每种版式的**每个文字槽位**都在
[templates/contracts.yaml](templates/contracts.yaml)
里声明了字数范围——数值来自实际渲染好看的真实文案，不是拍脑袋。

1. LLM 读文章后在契约范围内**填规格**
2. `validate.py` 在渲染前逐条机械校验，报**精确路径**：
   `card-03(chain).steps[1].text: 17.5 > max 15`
3. `measure.py` 让真实浏览器渲染，用 `getBBox()` 拿每个文本的**真实包围盒**，
   和 build 时埋进 HTML 的方框清单比对
4. 仍有溢出，编排流就校准自己的宽度估算器、必要时注入 `textLength`，再跑——最多 3 轮
5. 还压不下的文案进 `needs_llm` 清单——LLM 在这里介入，拿到的是精确报错而不是「看起来坏了」

两道门都是纯脚本：规格门便宜、拦住大多数问题；像素门贵而准、兜住剩余。
LLM 从头到尾不会被要求「把它弄好看」。

## 版式（13 种）

| 版式 | 形态 | 适合 |
|---|---|---|
| `cover` | **汇总封面**：标题 + 2×2 四宫格，每格一个微缩版式 | 封面 |
| `hub` | 标题 + 中心圆 + 概念框 | 讲并列概念的任意页 |
| `chain` | 竖排方框 + 箭头 | 步骤、循环 |
| `cycle` | 节点围成环 + 弧形箭头 | ReAct / PDCA |
| `spectrum` | 渐变箭头 + 两端标签 + 列表 | 「什么时候用 A 还是 B」 |
| `timeline` | 居中竖轴、左右交替 | 阶段、演进 |
| `flow` | 横排节点（可带底部一排） | 链路、数据流 |
| `bullets` | • 列表行自适应填满 | 坑、清单 |
| `compare` | 左右两列、内层块自适应 | 反例 vs 正解 |
| `matrix` | 2×2 四象限 | 按规模/维度选型 |
| `pyramid` | 梯形分层 | 能力层级、优先级分层 |
| `arch` | 嵌套框 + 箭头 + 底部一排 | 角色、架构 |
| `raw` | 内联 SVG 逃生舱 | 以上都不合适时 |

12 张版式实渲染样张（raw 不单独出样张）：[docs/images/layouts/](docs/images/layouts/)

装饰零件（齿轮、星形，全部是 SVG path，无位图）自动轮换：

![](docs/images/decor-sheet.png)

## 文案语法

`[[关键词]]` 给文字加马克笔底色（颜色自动轮换——蓝、黄、粉、绿、灰、橙）；
`[[关键词|b]]` 指定颜色。方框也能 `fill` 上色。

```yaml
- layout: chain
  title: Function Calling
  subtitle: "[[tool_call]] 是模型吐的，干活的是代码"
  steps:
    - {text: "① 注入 [[tools 定义]]"}
    - {text: "③ 模型返回 tool_calls", fill: yellow}
  note: "回到 ② 步，直到模型不再调工具"
```

## 依赖

| 依赖 | 必需？ | 说明 |
|---|---|---|
| Python 3.8+ | 必需 | 核心脚本只用标准库 |
| pyyaml | 可选 | 只有 .yaml 规格需要；**.json 规格零第三方依赖** |
| Chromium 浏览器 | 渲染必需 | Chrome / Edge / Chromium，自动探测 |
| 多模态模型 | 可选 | 正确性校验是纯文本度量；视觉只多一步审美终检 |

## 仓库结构

```
SKILL.md                  面向 Agent 的入口（工作流 + 契约 + 文案纪律）
scripts/ink.py            渲染核心：手绘原语 + 13 种版式 + 页面装配
scripts/decor.py          装饰零件（齿轮 / 星形，纯 SVG）
scripts/build.py          CLI：规格 → HTML
scripts/validate.py       CLI：字数契约校验（规格门）
scripts/render.py         CLI：HTML → PNG（跨平台浏览器探测）
scripts/measure.py        真实浏览器文本测量（像素门）
scripts/pipeline.py       LangGraph 风格编排：build → measure → 修正循环 → render
scripts/doctor.py         环境自检
templates/contracts.yaml  每种版式的字数预算（契约）
examples/                 5 份完整规格（yaml + json）
docs/images/              本 README 使用的渲染样张
```

## 许可

代码 MIT。内置字体（站酷快乐体）使用
[SIL Open Font License 1.1](assets/fonts/OFL.txt)——与 MIT 的分界见 LICENSE。
