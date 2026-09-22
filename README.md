# text-to-infographic

*7 套皮肤，把长文变成能直接发的小红书 / Instagram 图文 —— 文字永远清晰（不像 AI 生图那样糊字），同一份规格永远出同一套图，每页都能手改。*

[English](README.en.md) · [SKILL.md](SKILL.md) · [docs/](docs/)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![layouts: 15](https://img.shields.io/badge/layouts-15-blue.svg)](docs/layouts.md)
[![skins: 7](https://img.shields.io/badge/skins-7-purple.svg)](assets/style.md)
[![python: ≥3.8](https://img.shields.io/badge/python-%E2%89%A53.8-blue.svg)](pyproject.toml)

![一套 8 页的成品，暗夜终端皮肤，四页并排](docs/images/showcase/02-terminal.png)

[快速开始](#快速开始) · [出图效果](#出图效果) · [版式与皮肤](#版式与皮肤) · [规格语法](#规格语法) · [页数与四道门](#页数与四道门) · [许可](#许可)

---

## 快速开始

### 1 · 装

把这句话发给你的 Agent：

```text
帮我安装 text-to-infographic：irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
```

macOS / Linux 把 `install.ps1 | iex` 换成 `install.sh | bash`；GitHub 不通就把
`raw.githubusercontent.com/Chendestiny/text-to-infographic/main` 整段换成
`gitee.com/destinychen/text-to-infographic/raw/main`。两条随便挑 —— 脚本先探 GitHub（3 秒），
不通自动改走 Gitee 并在两个镜像间重试；装完自己 clone 到 `~/.agents/skills/`、探
Python / Chrome / 字体、补 `pyyaml`、跑 `doctor`。只想体检不写入：加 `-CheckOnly` / `--check-only`。

### 2 · 用

```text
用 text-to-infographic（~/.agents/skills/text-to-infographic）
把 D:\notes\article.md 转成小红书图文，输出到桌面
```

产出 `card-01.png …`（默认 2160×2880，3:4 的 2 倍图）。怎么读文章、怎么定页数、怎么出图都写在
[SKILL.md](SKILL.md) 里，Agent 自己会做：**页数跑 `run.py --plan` 拿答案**（不推公式）、
**容量跑 `run.py --budget`**（折行与缩放交给浏览器）、**四道门全过才交付**（出现 `needs_llm`
就改文案重跑，不许跳门）。

### 3 · 改代码

```bash
git clone https://github.com/Chendestiny/text-to-infographic && cd text-to-infographic
python -c "import yaml" || pip install pyyaml                                     # 硬依赖
python scripts/run.py examples/json/agent-roadmap.json --out out/demo            # 四道门 + 出图
python scripts/run.py examples/json/agent-roadmap.json --budget --no-render      # 只看每槽字数预算
python scripts/run.py examples/json/agent-roadmap.json --only 3 --out out/demo   # 单页返工（1~2 秒）
python scripts/run.py examples/json/agent-roadmap.json --theme blueprint --out out/demo   # 换皮肤
python tests/run.py                                                              # 自测 32 条，约 80 秒
python scripts/doctor.py                                                         # 环境自检
```

依赖只有 Python 3.8+、`pyyaml` 和任意 Chromium 浏览器（自动探测，字体已内置）—— `pyyaml`
是**规格门**要的（契约本体 `templates/contracts.yaml` 是 YAML），**写 `.json` 规格也省不掉**。
规格怎么写直接抄 [examples/](examples/)。

---

## 出图效果

同一份内容（8 页），**7 套皮肤**各挑 4 页并排 —— 全部由脚本渲染，不是设计稿：

![蜡笔纸感 · crayon](docs/images/showcase/01-crayon.png)

![暗夜终端 · terminal](docs/images/showcase/02-terminal.png)

![工程蓝图 · blueprint](docs/images/showcase/03-blueprint.png)

![方格稿纸 · grid](docs/images/showcase/04-grid.png)

![素白细线 · mono](docs/images/showcase/05-mono.png)

![复古报刊 · retro](docs/images/showcase/06-retro.png)

![北欧冷调 · nord](docs/images/showcase/07-nord.png)

---

## 版式与皮肤

**这是两件事**：版式决定「哪里放什么」，皮肤决定「长什么样」。15 × 7 随便组合，
**版式字段一个都不用改**。

![版式图鉴](docs/images/layouts/版式图鉴.png)

`cover` 四宫格封面 · `cover_title` 大字标题封面 · `cover_quote` 金句封面 · `hub` 中心圆 ·
`chain` 步骤链 · `cycle` 环形循环 · `spectrum` 光谱决策 · `timeline` 时间轴 ·
`flow` 横向链路 · `bullets` 清单 · `compare` 左右对照 · `matrix` 四象限 ·
`pyramid` 金字塔 · `arch` 结构图 · `raw` 内联 SVG 逃生舱

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

## 规格语法

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

## 页数与四道门

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

## 许可

代码 MIT。内置字体（站酷快乐体）使用 [SIL OFL 1.1](assets/fonts/OFL.txt)，
与 MIT 的分界见 [LICENSE](LICENSE) —— 它也是仓库里唯一的第三方资源。
安全边界见 [SECURITY.md](SECURITY.md)，改了什么见 [CHANGELOG.md](CHANGELOG.md)。
