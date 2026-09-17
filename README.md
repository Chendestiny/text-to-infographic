# text-to-infographic

> **把长文变成一套直接能发的小红书 / Instagram 图文** —— 封面 + 每页一个要点，3:4 竖版手绘卡片风。
> 你只管把文章交给它，像素全部由脚本决定。

[English](README.en.md) · [SKILL.md](SKILL.md) · [docs/](docs/)

文字始终清晰（不像 AI 生图那样糊字，中文尤甚），每一页都是能手改的规格而不是位图，
同一份规格重复跑永远出同一套图。模型只在**声明的字数预算内**写文案，
字号、留白、描边、配色全由代码决定：

```
文章.md ──> [LLM] spec.json ──> validate ──> build ──> measure（真实浏览器实测）──> PNG × N
```

---

## 🚀 快速开始

### 1 · 装：把这句话发给你的 Agent

**这是个 skill，不是命令行工具** —— 装它、用它都该让 Agent 兜底。下面这句直接复制给你在用的
Agent（dsh / Claude Code / Codex / zcode / Cursor… 任何能联网 + 能执行命令的都行）：

Windows（PowerShell）：

```text
帮我安装 text-to-infographic：irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
```

macOS / Linux / WSL：

```text
帮我安装 text-to-infographic：curl -fsSL https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.sh | bash
```

> **为什么发给 Agent，而不是让用户自己去敲 cmd**：脚本要 clone 到
> `~/.agents/skills/text-to-infographic`、探 Python、找 Chrome/Edge、按需补 `pyyaml`、
> 最后跑一遍 `doctor.py` —— 中间任何一步缺东西（没装 Python、浏览器不在默认路径），
> Agent 能当场判断并补上；更重要的是**装完 Agent 才知道该按 [SKILL.md](SKILL.md) 的五步流程走**，
> 而不是只会在终端里跑命令。
>
> 两个平台脚本做的是同一件事：clone + 环境检查 + doctor。
> 只想体检不写入：加 `-CheckOnly`（Windows）/ `--check-only`（macOS/Linux）。

### 2 · 用：还是对 Agent 说一句

装好之后不用记任何参数，直接把需求丢给它 —— 路径和文件名换成你自己的：

```text
用 text-to-infographic（~/.agents/skills/text-to-infographic）
把 D:\notes\article.md 转成小红书图文，输出到桌面
```

Agent 按 [SKILL.md](SKILL.md) 走五步：读文章 → 写规格 → 过规格门 → 跑流水线 → 交图。
产出是 `card-01.png …`，2160×2880（3:4 的 2 倍图）。

**页数参考区间 6–9 张**（小红书配图规范：官方上限 18 张、推荐 6–9 张）—— 页数由"切法"决定，
**不随文章行数增长**：张数 ≈ 1（封面）+ 章节数。228 行的文章是 7 张，1000 行的文章也是 8~10 张。

| 文章规模 | 张数（含封面） | 怎么承载 |
|---|---|---|
| ≤1.5k 字 / 1~2 节 | 4–5 | 一页一个要点 |
| 1.5k~3k 字 / 2~3 节 | 5–6 | 一页一个小节 |
| 3k~6k 字 / 4~6 节 | 6–8 | 一页 1~2 个小节，坑合并成一页 `bullets` |
| 6k~10k 字 / 6~10 节 | 8–12 | 一页一个主题（`meta.max_cards` 显式声明预算） |
| >10k 字 / 10+ 节 | **拆成系列**，每篇 6–8 张 | 不要单篇塞到 18 张 |

密度靠版式承载（一页 `bullets` 4~6 条 / `chain` 5~6 步 / `compare` 4+4 条），页数才压得住。
`validate.py` 会按这个区间提示：超预算报软约束，超过平台上限 18 张报硬违规。

### 3 · 给要改代码的人：自己敲

```bash
git clone https://github.com/Chendestiny/text-to-infographic
cd text-to-infographic
python scripts/validate.py spec/my-deck.json                     # 规格门：逐条核对字数预算
python scripts/pipeline.py spec/my-deck.json -o out/my-deck       # build → 实测 → 出图
```

- 规格是 **.json（零第三方依赖）** 或 .yaml（需 `pip install pyyaml`）；写法直接抄
  [examples/](examples/) 里现成的（拿 `examples/agent-roadmap.json` 跑一遍就有成品）
- 渲染需要任意 Chromium 系浏览器（Chrome / Edge / Chromium），自动探测
- 字体已内置，不用另外装
- Windows 上 `python` 不在 PATH 时改成 `py -3`

---

## 🖼 出图效果

一份长文进去，**9 张图**出来 —— 2160×2880（3:4 的 2 倍图），直接能发。挑 6 张，一行两张：

|  |  |
|---|---|
|![四宫格封面](docs/images/showcase/01-cover.png)|![左右对照](docs/images/showcase/02-compare.png)|
|![横向链路](docs/images/showcase/03-flow.png)|![环形循环](docs/images/showcase/04-cycle.png)|
|![竖向步骤链](docs/images/showcase/05-chain.png)|![光谱决策](docs/images/showcase/06-spectrum.png)|

第一张是**汇总封面**：2×2 四宫格，每格一个微缩版式——等于把目录画出来。之后每页一个要点。
按 `card-01 … card-09` 顺序发出去就是一套完整轮播，不需要再修图。

---

##  怎么保证不出丑：两道门、三道检查

每种版式的**每个文字槽位**都在 [templates/contracts.yaml](templates/contracts.yaml)
里声明了字数预算，数值来自实际渲染好看的真实文案——不是拍脑袋。文案是在预算内写出来的，
不是写完再祈祷能放下。

| 门 | 是什么 | 抓什么 |
|---|---|---|
| **规格门** `validate.py` | 纯字符串计算，毫秒级，零 token | 文案超预算，报**精确路径**：`card-03(chain).steps[1].text  17.5 > max 15` |
| **像素门** `measure.py` | 真实浏览器渲染，用 `getBBox()` 量**每个文本的真实包围盒** | 真实宽度溢出、画到画布外、压出方框、HTML 行撑破卡片底边 |
| **内容门**（像素门里） | 规格里登记过的每段文字都必须真的出现在图上 | 「既不溢出也不压框、但字根本没画出来」的**静默吞字**，以及被引擎截成「…」的断尾 |

压不下的文案会进 `needs_llm` 清单，让模型拿到精确报错而不是「看起来坏了」。
内容类问题不会再空跑几轮校准（脚本修不了），一轮就点名到具体哪一句。
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
scripts/decor.py          装饰图元（齿轮 / 星形，纯 SVG）
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
docs/images/showcase/     本 README 里那套真实跑批
install.ps1 / install.sh  一句话安装脚本（clone + 环境检查 + doctor），交给 Agent 执行
```

---

##  致谢

- README 里那套图是一次真实跑批的产物（示例文章：《一张图看懂 Agent》）——
  内容与工具无关，只是拿来当一份四千字左右的真实测试样本。
- 内置字体：**站酷快乐体（ZCOOL KuaiLe）**，仓库里唯一的第三方资源。

## 📄 许可

代码 MIT。内置字体使用 [SIL Open Font License 1.1](assets/fonts/OFL.txt)，
与 MIT 的分界见 [LICENSE](LICENSE)。