# text-to-infographic

*Seven skins that turn a long article into a ready-to-publish Xiaohongshu / Instagram carousel — text stays crisp (image generation garbles CJK), the same spec always renders the same deck, and every page stays hand-editable.*

[中文说明](README.md) · [SKILL.md](SKILL.md) · [docs/](docs/)

[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![PRs welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)
[![layouts: 15](https://img.shields.io/badge/layouts-15-blue.svg)](docs/layouts.md)
[![skins: 7](https://img.shields.io/badge/skins-7-purple.svg)](assets/style.md)
[![python: ≥3.8](https://img.shields.io/badge/python-%E2%89%A53.8-blue.svg)](pyproject.toml)

![One 8-page deck, Terminal skin, four pages side by side](docs/images/showcase/02-terminal.png)

[Quick start](#quick-start) · [What comes out](#what-comes-out) · [Layouts and skins](#layouts-and-skins) · [Spec syntax](#spec-syntax) · [Page count and gates](#page-count-and-gates) · [License](#license)

---

## Quick start

### 1 · Install

Send this line to your agent:

```text
帮我安装 text-to-infographic：irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
```

On macOS / Linux swap `install.ps1 | iex` for `install.sh | bash`; if GitHub is unreachable, replace
`raw.githubusercontent.com/Chendestiny/text-to-infographic/main` with
`gitee.com/destinychen/text-to-infographic/raw/main`. Either line works — the script probes GitHub first
(3 s), falls back to the Gitee mirror and retries across both; once running it clones into
`~/.agents/skills/`, probes Python / Chrome / the bundled font, installs `pyyaml` if missing and runs
`doctor`. Inspect only, write nothing: add `-CheckOnly` / `--check-only`.

### 2 · Use

```text
Use text-to-infographic (~/.agents/skills/text-to-infographic)
Turn D:\notes\article.md into a Xiaohongshu carousel, save the images to my desktop
```

Output is `card-01.png …` (2160×2880 by default, 3:4 @2x). How to read the article, choose the page
count and render is all in [SKILL.md](SKILL.md) — the agent handles it: **the page count comes from
`run.py --plan`** (never derived by hand), **capacity comes from `run.py --budget`** (wrapping and
shrinking are the browser's job), and **all four gates must pass** before delivery (`needs_llm` means
shortening copy and re-running, never skipping).

### 3 · Change the code

```bash
git clone https://github.com/Chendestiny/text-to-infographic && cd text-to-infographic
python -c "import yaml" || pip install pyyaml                                     # hard requirement
python scripts/run.py examples/json/agent-roadmap.json --out out/demo            # four gates + render
python scripts/run.py examples/json/agent-roadmap.json --budget --no-render      # slot budgets only
python scripts/run.py examples/json/agent-roadmap.json --only 3 --out out/demo   # rework one page (1-2s)
python scripts/run.py examples/json/agent-roadmap.json --theme blueprint --out out/demo   # switch skin
python tests/run.py                                                              # self-test: 32 checks, ~80s
python scripts/doctor.py                                                         # environment self-check
```

The only dependencies are Python 3.8+, `pyyaml` and any Chromium browser (auto-detected; the font is
bundled) — `pyyaml` is needed by the **spec gate** (the contract itself, `templates/contracts.yaml`, is
YAML), so writing `.json` specs does not remove it.
Copy a spec shape from [examples/](examples/).

---

## What comes out

One deck of 8 pages, rendered under **7 skins**, 4 pages from each shown side by side — all produced
by scripts, not by a designer:

![Crayon Paper · crayon](docs/images/showcase/01-crayon.png)

![Terminal · terminal](docs/images/showcase/02-terminal.png)

![Blueprint · blueprint](docs/images/showcase/03-blueprint.png)

![Grid Paper · grid](docs/images/showcase/04-grid.png)

![Mono Swiss · mono](docs/images/showcase/05-mono.png)

![Retro Print · retro](docs/images/showcase/06-retro.png)

![Nord · nord](docs/images/showcase/07-nord.png)

---

## Layouts and skins

**These are two separate things**: the layout decides *what goes where*, the skin decides *what it
looks like*. Any of the 15 × 7 combinations works, and **not a single layout field changes**.

![layout gallery](docs/images/layouts/版式图鉴.png)

`cover` 2×2 summary cover · `cover_title` big-title cover · `cover_quote` quote cover ·
`hub` hub circle · `chain` step chain · `cycle` cycle · `spectrum` spectrum ·
`timeline` timeline · `flow` horizontal flow · `bullets` checklist · `compare` side-by-side ·
`matrix` 2×2 quadrants · `pyramid` tiers · `arch` architecture · `raw` raw inline SVG

| `meta.theme` | family | what it looks like |
|---|---|---|
| `crayon` | paper | cream paper + warm-grey hand-drawn strokes + crayon bands. **Default** |
| `grid` | paper | pale cream + light blue grid + blue-black ink |
| `retro` | paper | newsprint cream + dark brown ink + heavy underlines |
| `terminal` | diagram | dark navy + neon-green hairlines + grid, monospace |
| `blueprint` | diagram | dark blue + cold-white hairlines + a double coordinate grid |
| `mono` | diagram | white + black hairlines, the most restrained |
| `nord` | diagram | dark grey-blue + polar palette (frost blue / aurora green / purple) |

**The two families draw nodes differently**: paper skins distinguish nodes with *filled blocks*;
diagram skins use a *transparent fill + a theme-colored hairline + corner ticks*, never a saturated
fill. Fields, budgets and all four gates stay identical.
Details: [docs/layouts.md](docs/layouts.md) (layout fields) · [assets/style.md](assets/style.md) (skin tokens).

Pick a skin / tune the node drawing: `python make_theme_gallery.py --family paper` (writes to the
Desktop), `python make_style_probe.py` (columns = skins, rows = box styles).

---

## Spec syntax

`[[keyword]]` adds a highlighter band (the color rotates per skin); `[[word|b]]` pins a color
(`b` blue / `y` yellow / `p` pink / `gr` green / `g` gray / `o` orange).
Boxes are filled by default — write `"fill": "none"` to leave one blank and say "this step is minor".

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

## Page count and gates

**Run the script for the page count** instead of deriving it, and let *measurement* decide capacity
rather than memorised budgets:

```bash
python scripts/run.py --plan <article.md>   # characters/sections → suggested count + range + per-page skeleton
python scripts/run.py <spec> --budget       # per-slot size and starting font size (before writing copy)
```

| gate | what it catches |
|---|---|
| preflight | quantity words that disagree with the actual number of items |
| spec gate | unknown fields / out-of-range item counts / page count over the hard cap (over-budget copy is only a notice, with an exact path) |
| pixel gate | real-browser measurement: does not fit, drawn off-canvas, crossing a box or line, two runs of text overlapping |
| content gate | **silently swallowed text** — copy registered in the spec that never made it onto the card, or got truncated to "…" |

All four gates live inside one command and it ends with a verdict (page count lands in 4–9;
6–9 is the platform sweet spot):

```bash
python scripts/run.py <spec.json> --article <article.md> --out <dir>   # deliver
python scripts/run.py <spec.json> --only 3 --out <dir>                 # rework one page (1-2s)
```

---

## License

Code is MIT. The bundled font (ZCOOL KuaiLe) is under
[SIL OFL 1.1](assets/fonts/OFL.txt); the boundary between the two is in [LICENSE](LICENSE) — it is
also the only third-party asset in the repo.
Usage boundaries: [SECURITY.md](SECURITY.md); what changed: [CHANGELOG.md](CHANGELOG.md).
