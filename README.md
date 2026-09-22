# text-to-infographic

> **把长文变成一套直接能发的小红书 / Instagram 图文** —— 封面 + 每页一个要点，3:4 竖版，7 套皮肤可选。
> 你只管把文章交给它，像素全部由脚本决定。

[English](README.en.md) · [SKILL.md](SKILL.md) · [docs/](docs/)

文字始终清晰（不像 AI 生图那样糊字，中文尤甚），每一页都是能手改的规格而不是位图，
同一份规格重复跑永远出同一套图。模型只在**声明的字数预算内**写文案，
字号、留白、描边、配色全由代码决定：

```
文章.md ──> run.py --plan ──> [LLM] spec.json ──> run.py（四道门 + 出图）──> PNG × N
```

---

## 🚀 快速开始

### 1 · 装：把这句话发给你的 Agent

**Windows（PowerShell）：**

```text
帮我安装 text-to-infographic：irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
```

**macOS / Linux / WSL：**

```text
帮我安装 text-to-infographic：curl -fsSL https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.sh | bash
```

**国内网络：走 Gitee 镜像（内容与 GitHub 同步）**

```text
帮我安装 text-to-infographic：irm https://gitee.com/destinychen/text-to-infographic/raw/main/install.ps1 | iex
```

```text
帮我安装 text-to-infographic：curl -fsSL https://gitee.com/destinychen/text-to-infographic/raw/main/install.sh | bash
```

> **两个仓库随便挑一条**：脚本会先探一下 GitHub（3 秒），探不通就自动改走 Gitee 镜像；
> 克隆失败还会在两个镜像之间自动重试。想指定仓库：`-Repo <url>`（Windows）/ `--repo <url>`，
> 或环境变量 `T2I_REPO`。
>
> 这是个 skill，装它、用它都让 Agent 兜底：脚本会 clone 到 `~/.agents/skills/`、探 Python / Chrome / 字体、
> 缺 `pyyaml` 按需补、最后跑一遍 `doctor`。只想体检不写入：加 `-CheckOnly`（Windows）/ `--check-only`。

### 2 · 用：还是对 Agent 说一句

```text
用 text-to-infographic（~/.agents/skills/text-to-infographic）
把 D:\notes\article.md 转成小红书图文，输出到桌面
```

其余都写在 [SKILL.md](SKILL.md) 里，Agent 自己会做：

| Agent 会自动做的事 | 依据 |
|---|---|
| 装完 clone + 探环境 + 跑 `doctor`，缺依赖自己补 | 安装脚本 |
| 按五步走：读文章 → 写规格 → **过规格门** → 跑流水线 → 交图 | SKILL.md 第 1~5 步 |
| 页数**跑 `run.py --plan` 拿答案**（含页骨架），不自己推公式 | SKILL.md 第 2 步 + `scripts/run.py --plan` |
| 容量**跑 `run.py --budget` 看槽尺寸**（折行/缩放交给浏览器），不靠背字数上限 | `scripts/run.py --budget` |
| 四道门都要过；出现 `needs_llm` 就改文案重跑，不许跳门 | SKILL.md 第 4~5 步 |
| **复核看拼版图**（720px 缩略图 + 2×2 拼版，一次 4 张），只问断词/孤字/压字/数量词 | `scripts/review_sheet.py` |
| 每次跑完把**逐页体检表 + 问题明细**摊开（`dom-overflow` / `dom-orphan` / 压框 / 重叠，逐卡点名），不藏问题 | `scripts/pipeline.py` |
| 用 **rect 求交**查压字/压线/穿框（不用视觉模型），视觉只留最后一道审美抽查 | `scripts/measure.py` |
| 交付时给门禁**逐字输出** + 页数理由 + 降级报告 + 自检结论 | SKILL.md 第 6 步 |

产出是 `card-01.png …`，默认 2160×2880（3:4 的 2 倍图；`render.py --scale 1` 可出 1080×1440）。

### 3 · 给要改代码的人：自己敲

```bash
git clone https://github.com/Chendestiny/text-to-infographic
cd text-to-infographic
python -c "import yaml" || pip install pyyaml                                     # 硬依赖
python scripts/run.py examples/json/agent-roadmap.json --out out/demo            # 四道门 + 出图
python scripts/run.py examples/json/agent-roadmap.json --budget --no-render      # 只看每槽字数预算
python scripts/run.py examples/json/agent-roadmap.json --only 3 --out out/demo   # 单页返工（1~2 秒）
python scripts/run.py examples/json/agent-roadmap.json --theme blueprint --out out/demo   # 换皮肤
python tests/run.py                                                              # 自测（改代码前/后跑）
```

- 依赖只有 Python 3.8+、`pyyaml` 和任意 Chromium 浏览器（自动探测），字体已内置；
  `pyyaml` 是**规格门**要的（契约本体 `templates/contracts.yaml` 是 YAML），**写 `.json` 规格也省不掉**
- 规格怎么写直接抄 [examples/](examples/)（拿 `examples/agent-roadmap.json` 跑一遍就有成品）

---

## 🖼 出图效果

同一份内容（8 页），**7 套皮肤**各挑 4 页并排 —— 全部由脚本渲染，不是设计稿：

![蜡笔纸感 · crayon](docs/images/showcase/01-crayon.png)

![暗夜终端 · terminal](docs/images/showcase/02-terminal.png)

![工程蓝图 · blueprint](docs/images/showcase/03-blueprint.png)

![方格稿纸 · grid](docs/images/showcase/04-grid.png)

![素白细线 · mono](docs/images/showcase/05-mono.png)

![复古报刊 · retro](docs/images/showcase/06-retro.png)

![北欧冷调 · nord](docs/images/showcase/07-nord.png)

---

## 🧩 版式 15 种 · 皮肤 7 套

**这是两件事**：版式决定「哪里放什么」，皮肤决定「长什么样」。15 × 7 随便组合，
**版式字段一个都不用改**。

![版式图鉴](docs/images/layouts/版式图鉴.png)

`cover` 四宫格封面 · `cover_title` 大字标题封面 · `cover_quote` 金句封面 · `hub` 中心圆 ·
`chain` 步骤链 · `cycle` 环形循环 · `spectrum` 光谱决策 · `timeline` 时间轴 ·
`flow` 横向链路 · `bullets` 清单 · `compare` 左右对照 · `matrix` 四象限 ·
`pyramid` 金字塔 · `arch` 结构图 · `raw` 内联 SVG 逃生舱

![皮肤图鉴](docs/images/themes/皮肤图鉴.png)

| `meta.theme` | 族 | 长什么样 |
|---|---|---|
| `crayon` | 纸张 | 米黄纸底 + 暖灰手绘笔锋 + 蜡笔色带。**默认** |
| `grid` | 纸张 | 浅米底 + 淡蓝方格 + 蓝黑墨水 |
| `retro` | 纸张 | 米黄报纸底 + 深褐墨水 + 粗下划线 |
| `terminal` | 工程 | 深藏蓝底 + 荧光绿细线 + 网格，等宽字 |
| `blueprint` | 工程 | 深蓝底 + 冷白细线 + 双层坐标网格 |
| `mono` | 工程 | 白底 + 黑细线，留白最狠 |
| `nord` | 工程 | 深灰蓝底 + 极地色系（霜蓝/极光绿/紫） |

**两个族的画法不同**：纸张族靠「上色方框」区分节点；工程族靠「透明底 + 主题色细描边 +
四角刻度」，不做高饱和填充。字段、字数、四道门口径完全一致。
细节：[docs/layouts.md](docs/layouts.md)（版式字段）· [assets/style.md](assets/style.md)（皮肤令牌）。

挑皮肤 / 调节点画法：`python make_theme_gallery.py --family paper`（→ 桌面）、
`python make_style_probe.py`（列 = 皮肤，行 = 方框方案）。

---

## ✍️ 规格语法

`[[关键词]]` 加马克笔底色（颜色按皮肤轮换），`[[词|b]]` 指定色
（`b` 蓝 / `y` 黄 / `p` 粉 / `gr` 绿 / `g` 灰 / `o` 橙）。
方框默认上色，想让某框留白表达「这步不重要」写 `"fill": "none"`。

```yaml
meta: { theme: crayon, footer: "" }
cards:
  - layout: chain
    title: Function Calling
    subtitle: "[[tool_call]] 是模型吐的，干活的是代码"
    steps:
      - {text: "① 注入 [[tools 定义]]"}
      - {text: "③ 模型返回 tool_calls", fill: yellow}
    note: "回到 ② 步，直到模型不再调工具"
```

---

## 🛡 页数与四道门

页数**跑脚本拿答案**，不自己推公式；**容量也是实测说话**，不靠背字数上限：

```bash
python scripts/run.py --plan <文章.md>     # 汉字数/节数 → 建议张数 + 区间 + 每页骨架
python scripts/run.py <spec> --budget      # 每槽尺寸与起手字号（写文案前看）
```

| 门 | 抓什么 |
|---|---|
| 预检 | 数量词与规格里实际的条数对不上 |
| 规格门 | 未知字段 / 条数越界 / 页数超硬上限（字数超预算只提示，报精确路径） |
| 像素门 | 真实浏览器实测：放不下、画出画布、压框压线、两段文字互相压住 |
| 内容门 | **静默吞字** —— 规格里登记过的字根本没画出来、或被截成「…」 |

四道门全在一条命令里，跑完直接给结论（页数落在 4~9，6~9 是平台偏好区）：

```bash
python scripts/run.py <spec.json> --article <文章.md> --out <目录>   # 交付
python scripts/run.py <spec.json> --only 3 --out <目录>              # 单页返工（1~2 秒）
```

---

## 📦 装上就能跑

Python 3.8+ · `pyyaml`（规格门要读契约本体，写 `.json` 也省不掉）· 任意 Chromium 浏览器（自动探测）。
字体已内置，不需要联网，不需要多模态模型（正确性是纯文本度量）。

```bash
python scripts/doctor.py    # 环境自检
python tests/run.py         # 自测 32 条，约 80 秒
```

入口与手册：`SKILL.md`（Agent 手册）· `scripts/run.py`（唯一入口）· `scripts/ink.py`（渲染核心）·
`scripts/theme.py`（皮肤令牌）· `templates/contracts.yaml`（字数契约）· `examples/`（5 份完整规格）·
`docs/` · `tests/`。改代码先看 [CONTRIBUTING.md](CONTRIBUTING.md)，改了什么看 [CHANGELOG.md](CHANGELOG.md)。

---

## 📄 许可

代码 MIT。内置字体（站酷快乐体）使用 [SIL OFL 1.1](assets/fonts/OFL.txt)，
与 MIT 的分界见 [LICENSE](LICENSE) —— 它也是仓库里唯一的第三方资源。
使用边界见 [SECURITY.md](SECURITY.md)。
