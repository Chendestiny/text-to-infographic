# text-to-infographic

> **把长文变成一套直接能发的小红书 / Instagram 图文** —— 封面 + 每页一个要点，3:4 竖版手绘卡片风。
> 你只管把文章交给它，像素全部由脚本决定。

[English](README.md) · [SKILL.md](SKILL.md) · [docs/](docs/)

文字始终清晰（不像 AI 生图那样糊字，中文尤甚），每一页都是能手改的规格而不是位图，
同一份规格重复跑永远出同一套图。

---

## 🖼 出图效果

一次真实跑批：《一张架构图说清楚 Agent + ReAct 循环 + Workflow》→ **9 张**，2160×2880（3:4 的 2 倍图）。
挑 6 张，一行两张：

|  |  |
|---|---|
|![四宫格封面](docs/images/showcase/01-cover.png)|![左右对照](docs/images/showcase/02-compare.png)|
|![横向链路](docs/images/showcase/03-flow.png)|![环形循环](docs/images/showcase/04-cycle.png)|
|![竖向步骤链](docs/images/showcase/05-chain.png)|![光谱决策](docs/images/showcase/06-spectrum.png)|

第一张是**汇总封面**：2×2 四宫格，每格一个微缩版式——等于把目录画出来。之后每页一个要点。
按 `card-01 … card-09` 顺序发出去就是一套完整轮播，不需要再修图。

---

## 🚫 为什么不让模型直接画？

AI 生图的致命伤是文字必糊，中文尤其明显。让 LLM 自由发挥写 HTML「信息图」则是每次都不一样：
间距不一致、文字出框、版式一次性，没法当产品用。

所以把 LLM 挪到它擅长的地方（读文章、定结构、压文案），像素交给确定性渲染器：

```
文章.md ──> [LLM] spec.json ──> validate ──> build ─> measure（真实浏览器实测）──> PNG × N
              只有这一步需要     规格门      HTML      像素门 + 修正循环
              LLM
```

LLM 从头到尾碰不到字号、留白、描边。它只做一件事：在**声明的字数预算内**写文案，
其余全由脚本决定——这正是「可复现」和「每页可手改」的来源。

---

## 🚀 快速开始

```bash
git clone https://github.com/Chendestiny/text-to-infographic
cd text-to-infographic

python scripts/doctor.py                                          # 环境自检
python scripts/pipeline.py examples/agent-roadmap.json -o out/    # 全流程 -> out/card-*.png
```

- Windows 上若 `python` 不在 PATH，改用 `py -3`
- 规格支持 **.json（零第三方依赖）** 或 .yaml（需 `pip install pyyaml`）
- 渲染需要任意 Chromium 系浏览器（Chrome / Edge / Chromium），自动探测
- 字体已内置，不需要额外安装

面向 Agent 的工作流看 [SKILL.md](SKILL.md)；细节手册在 [docs/](docs/)。

---

## 🧭 怎么保证不出丑：两道门、三道检查

每种版式的**每个文字槽位**都在 [templates/contracts.yaml](templates/contracts.yaml)
里声明了字数预算，数值来自实际渲染好看的真实文案——不是拍脑袋。文案是在预算内写出来的，
不是写完再祈祷能放下。

| 门 | 是什么 | 抓什么 |
|---|---|---|
| **规格门** `validate.py` | 纯字符串计算，毫秒级，零 token | 文案超预算，报**精确路径**：`card-03(chain).steps[1].text  17.5 > max 15` |
| **像素门** `measure.py` | 真实浏览器渲染，用 `getBBox()` 量**每个文本的真实包围盒** | 真实宽度溢出、画到画布外、压出方框、HTML 行撑破卡片底边 |
| **内容门**（像素门里） | 规格里登记过的每段文字都必须真的出现在图上 | 「既不溢出也不压框、但字根本没画出来」的**静默吞字** |

压不下的文案会进 `needs_llm` 清单，让模型拿到精确报错而不是「看起来坏了」。
编排流还会自己校准宽度估算器、必要时注入 `textLength`，最多重跑 3 轮再求援。
细节：[docs/contracts.md](docs/contracts.md) · [docs/architecture.md](docs/architecture.md)。

---

## 🧩 版式（13 种）

| 版式 | 形态 | 适合 |
|---|---|---|
| `cover` | **汇总封面**：标题 + 2×2 四宫格，每格一个微缩版式 | 封面 |
| `hub` | 标题 + 中心圆 + 概念框 | 讲并列概念 |
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
| `raw` | 内联 SVG 逃生舱 | 以上都表达不了时 |

<details>
<summary><b>12 张版式实渲染样张</b>（raw 不单独出样张，点开看）</summary>

|  |  |
|---|---|
|![cover](docs/images/layouts/方案-01-cover-四宫格封面.png)|![hub](docs/images/layouts/方案-02-hub-中心圆.png)|
|![chain](docs/images/layouts/方案-03-chain-步骤链.png)|![cycle](docs/images/layouts/方案-04-cycle-环形循环.png)|
|![spectrum](docs/images/layouts/方案-05-spectrum-光谱决策.png)|![timeline](docs/images/layouts/方案-06-timeline-时间轴.png)|
|![flow](docs/images/layouts/方案-07-flow-横向链路.png)|![compare](docs/images/layouts/方案-08-compare-左右对照.png)|
|![bullets](docs/images/layouts/方案-09-bullets-清单.png)|![matrix](docs/images/layouts/方案-10-matrix-四象限.png)|
|![pyramid](docs/images/layouts/方案-11-pyramid-金字塔.png)|![arch](docs/images/layouts/方案-12-arch-结构图.png)|

</details>

装饰零件（齿轮、星形，全是 SVG path，无位图）自动轮换；汇总封面会跳过装饰，
免得压到四宫格的边框上：

![装饰零件图鉴](docs/images/decor-sheet.png)

---

## ✍️ 文案语法

`[[关键词]]` 给文字加马克笔底色（颜色自动轮换：蓝 → 黄 → 粉 → 绿 → 灰 → 橙）；
`[[关键词|b]]` 指定颜色。方框同样能用 `fill`，而且默认全部上色——
想让某个框留白表达「这步不重要」才写 `fill: none`。

```yaml
- layout: chain
  title: Function Calling
  subtitle: "[[tool_call]] 是模型吐的，干活的是代码"
  steps:
    - {text: "① 注入 [[tools 定义]]"}
    - {text: "③ 模型返回 tool_calls", fill: yellow}
  note: "回到 ② 步，直到模型不再调工具"
```

---

## 📦 依赖

| 依赖 | 必需？ | 说明 |
|---|---|---|
| Python 3.8+ | 必需 | 核心脚本只用标准库 |
| pyyaml | 可选 | 只有 .yaml 规格需要；**.json 规格零第三方依赖** |
| Chromium 浏览器 | 渲染必需 | Chrome / Edge / Chromium，自动探测（CDP 或 CLI 后端） |
| 多模态模型 | 可选 | 正确性校验是纯文本度量；视觉只多一步审美终检 |

## 📁 仓库结构

```
SKILL.md                  面向 Agent 的入口（工作流 + 契约 + 文案纪律）
scripts/ink.py            渲染核心：手绘原语 + 13 种版式 + 页面装配
scripts/decor.py          装饰零件（齿轮 / 星形，纯 SVG）
scripts/build.py          CLI：规格 → HTML
scripts/validate.py       CLI：字数契约校验（规格门）
scripts/render.py         CLI：HTML → PNG（浏览器探测）
scripts/measure.py        真实浏览器文本测量（像素门 + 内容门）
scripts/pipeline.py       build → measure → 修正循环 → render，最多 3 轮
scripts/doctor.py         环境自检
scripts/vision_probe.py   一次性判定当前模型能不能真的读图
templates/contracts.yaml  每种版式的字数预算（契约）
examples/                 5 份完整规格（.json 与 .yaml 各一套）
docs/                     手册：版式、契约、渲染、排障、扩展
docs/images/showcase/     本 README 顶部那套真实跑批
```

---

## 🙏 致谢

- 顶部这套图是用作者自己的文章《一张架构图说清楚 Agent + ReAct 循环 + Workflow》跑出来的——
  内容与工具无关，只是拿来当一份够长的真实测试样本。
- 内置字体：**站酷快乐体（ZCOOL KuaiLe）**，仓库里唯一的第三方资源。

## 📄 许可

代码 MIT。内置字体使用 [SIL Open Font License 1.1](assets/fonts/OFL.txt)，
与 MIT 的分界见 [LICENSE](LICENSE)。