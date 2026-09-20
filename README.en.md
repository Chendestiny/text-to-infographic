# text-to-infographic

> **Turn a long article into a ready-to-publish 3:4 card carousel** — a cover plus one page per key
> point, hand-drawn card style. You hand it the article; the scripts own every pixel.

[中文说明](README.md) · [SKILL.md](SKILL.md) · [docs/](docs/)

Text is always crisp (never garbled the way image generation renders CJK), every page stays
hand-editable, and the same spec always renders the same set of images — byte for byte.
The model writes copy inside a declared character budget; fonts, spacing, strokes and colors are
decided by code:

```
article.md ──> run.py --plan ──> [LLM] spec.json ──> run.py (four gates + render) ──> PNG × N
```

---

## 🚀 Quick start

### 1 · Install: send this line to your agent

**Windows (PowerShell):**

```text
帮我安装 text-to-infographic：irm https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.ps1 | iex
```

**macOS / Linux / WSL:**

```text
帮我安装 text-to-infographic：curl -fsSL https://raw.githubusercontent.com/Chendestiny/text-to-infographic/main/install.sh | bash
```

**Behind the Great Firewall: use the Gitee mirror** (same content, kept in sync with GitHub)

```text
帮我安装 text-to-infographic：irm https://gitee.com/destinychen/text-to-infographic/raw/main/install.ps1 | iex
```

```text
帮我安装 text-to-infographic：curl -fsSL https://gitee.com/destinychen/text-to-infographic/raw/main/install.sh | bash
```

> **Pick either line** — the script probes GitHub first (3 s) and falls back to the Gitee mirror when
> it cannot reach it; if a clone fails it retries against the other mirror. Pin a repo explicitly with
> `-Repo <url>` (Windows) / `--repo <url>`, or the `T2I_REPO` environment variable.
>
> This is a skill, so let the agent drive both the install and the usage: the script clones into
> `~/.agents/skills/`, probes Python / Chrome / the bundled font, installs `pyyaml` if it is
> missing, and finally runs `doctor`. Inspect only, write nothing: `-CheckOnly` (Windows) /
> `--check-only` (macOS/Linux).

### 2 · Use: one more line to your agent

```text
Use text-to-infographic (~/.agents/skills/text-to-infographic)
Turn D:\notes\article.md into a Xiaohongshu carousel, save the images to my desktop
```

Everything else lives in [SKILL.md](SKILL.md), and the agent does it on its own:

| What the agent does automatically | Where it is mandated |
|---|---|
| Clones, probes the environment, runs `doctor`, fixes what is missing | install script |
| Five steps: read → write spec → **pass the spec gate** → run the pipeline → deliver | SKILL.md steps 1–5 |
| Gets the page count by **running `run.py --plan`**, not by deriving it | SKILL.md step 2 + `scripts/run.py --plan` |
| Gets slot sizes by **running `run.py --budget`** (wrapping and shrinking are the browser's job), not by memorising budgets | `scripts/run.py --budget` |
| All four gates must pass; `needs_llm` means shortening copy and re-running, never skipping | SKILL.md steps 4–5 |
| **Reviews the contact sheet** (720px thumbnails, 4 per sheet) for broken words, orphan lines, overlap, mismatched counts | `scripts/review_sheet.py` |
| Prints a per-card health table plus the specific problems (`dom-overflow` / `dom-orphan` / box or line crossings), naming each card | `scripts/pipeline.py` |
| Uses **rect intersection** for overlap checks instead of a vision model; vision is only a final aesthetic spot-check | `scripts/measure.py` |
| Reports the gate output **verbatim** + page-count reasoning + degradation report + self-check result | SKILL.md step 6 |

Output is `card-01.png …`, 2160×2880 by default (3:4 @2x; `render.py --scale 1` gives 1080×1440).

### 3 · Or drive it yourself (if you want to change the code)

```bash
git clone https://github.com/Chendestiny/text-to-infographic
cd text-to-infographic
python scripts/run.py examples/json/agent-roadmap.json --out out/demo           # four gates + render
python scripts/run.py examples/json/agent-roadmap.json --budget --no-render     # slot budgets only
```

- The only dependencies are Python 3.8+ and any Chromium browser (auto-detected); the font is bundled; `.json` specs need zero third-party packages
- Copy a spec shape from [examples/](examples/) — running `examples/agent-roadmap.json` gives you a finished deck

---

## 🖼 What comes out

One long-form draft in, **9 cards** out — 2160×2880 (3:4 @2x), ready to post. Six of them, two per row
(this is a real run, not a design mock-up):

|  |  |
|---|---|
|![summary cover](docs/images/showcase/01-cover.png)|![compare](docs/images/showcase/02-compare.png)|
|![flow](docs/images/showcase/03-flow.png)|![cycle](docs/images/showcase/04-cycle.png)|
|![chain](docs/images/showcase/05-chain.png)|![spectrum](docs/images/showcase/06-spectrum.png)|

The first card is a **summary cover**: a 2×2 grid where each quadrant is a miniature layout — the
table of contents, drawn. Every card after it carries one idea. Publish them in `card-01 … card-09`
order and the carousel is done; nothing needs retouching.

---

## 📐 How many cards

**Recommended range: 4–9 cards (cover included)** — 6–9 is what Xiaohongshu prefers, short posts at
4–5 are fine, and the platform hard limit is 18. The rule and the per-size table are defined in
**exactly one place**: [SKILL.md](SKILL.md) step 2 (three competing versions used to make the model
second-guess itself). When you actually need the number, **run the script instead of deriving it**:

```bash
python scripts/run.py --plan <article.md>   # chars / sections → suggested count + range + per-card skeleton
```

**Budgets work the same way**: the character counts in the contract are only *writing advice* — whether
copy actually fits is decided by a **real browser**. `python scripts/run.py <spec.json> --budget` prints
each slot's size and starting font size. When rendering, `pipeline.py` also prints a per-card health
table and names `dom-overflow` / `dom-orphan` / box or line crossings / overlap.

---

## 🧭 How it stays correct: four gates

Every layout declares a **character budget for every text slot** in
[templates/contracts.yaml](templates/contracts.yaml), measured from renders that actually look good —
not guessed. Copy is written *inside* that budget instead of hoping it fits.

| gate | what it is | catches |
|---|---|---|
| **preflight** `preflight.py` | pure string math, milliseconds, zero tokens | quantity words that disagree with the number of items the spec actually lists ("3 things" but five rows) |
| **spec gate** `validate.py` | renders once without a browser to compute geometry, milliseconds, zero tokens | structural problems (unknown fields / a `note` that never renders / item counts out of range / page count past the hard limit) + the **geometry wall**; over-budget copy is only a notice |
| **pixel gate** `measure.py` | renders in a real browser and measures every **DOM text slot** and box rectangle | `dom-overflow` (genuinely does not fit), text past the canvas, text spilling out of its box, overlapping text |
| **content gate** (inside the pixel gate) | every string the spec registered must actually appear in the render | text that is neither overflowing nor clipped but simply **never drawn**, plus tails replaced with an ellipsis |

All four run inside a single command that ends with a verdict:
`python scripts/run.py <spec.json> --article <article.md> --out <dir>`.
Misfit copy is escalated as a `needs_llm` list, so the model gets a precise error instead of "it looks
broken". Content and layout problems skip the retry loop (scripts cannot fix them) and come back
naming the exact sentence. Full detail: [docs/contracts.md](docs/contracts.md) · [docs/architecture.md](docs/architecture.md).

---

## 🧩 Layouts (13)

| layout | shape | use for |
|---|---|---|
| `cover` | **summary cover**: title + 2×2 grid of mini layouts | first page |
| `hub` | title + hub circle + concept boxes | parallel concepts |
| `chain` | vertical boxes + arrows | steps, loops |
| `cycle` | nodes on a circle, curved arrows | ReAct / PDCA |
| `spectrum` | gradient arrow + end labels + list | "A or B?" trade-offs |
| `timeline` | centered vertical axis, alternating labels | stages, evolution |
| `flow` | horizontal nodes (+ bottom strip) | pipelines, data flow |
| `bullets` | bullet rows that stretch to fill | pitfalls, checklists |
| `compare` | two columns, inner blocks auto-fit | do / don't |
| `matrix` | 2×2 quadrants | pick by scale or dimension |
| `pyramid` | stacked trapezoid tiers | capability levels, priorities |
| `arch` | nested boxes + arrow + chip row | roles, architecture |
| `raw` | inline SVG escape hatch | anything the above cannot express |

<details>
<summary><b>All 12 rendered layout samples</b> (raw has none — click to expand)</summary>

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

## ✍️ Spec syntax

`[[keyword]]` paints a marker-pen highlight behind the text (colors rotate: blue → yellow → pink →
green → gray → orange); `[[keyword|b]]` pins a color. Boxes take `fill` the same way, and boxes are
filled by default — write `fill: none` to leave one blank on purpose.

```yaml
- layout: chain
  title: Function Calling
  subtitle: "[[tool_call]] is emitted by the model — your code does the work"
  steps:
    - {text: "① inject the [[tools definition]]"}
    - {text: "③ the model returns tool_calls", fill: yellow}
  note: "loop back to ② until the model stops calling tools"
```

---

## 📦 Requirements

| dependency | required? | notes |
|---|---|---|
| Python 3.8+ | yes | core scripts are stdlib-only |
| pyyaml | optional | only for .yaml specs; **.json specs need zero third-party packages** |
| Chromium browser | to render | Chrome / Edge / Chromium, auto-detected (CDP or CLI backend) |
| multimodal model | optional | correctness is pure text measurement; vision only adds an aesthetic last pass |

## 📁 Repository layout

```
SKILL.md                  agent-facing entry point (workflow, contract, copy discipline)
scripts/run.py            the single entry point: --plan / --budget / deliver (four gates + render + report)
scripts/ink.py            rendering core: hand-drawn primitives + 13 layouts + page assembly
scripts/decor.py          decoration parts (gears / stars, pure SVG)
scripts/build.py          CLI: spec → HTML
scripts/plan.py           CLI: page planning (two-level cut; suggested count + per-card skeleton)
scripts/preflight.py      CLI: text preflight (quantity words vs actual item counts)
scripts/capacity.py       CLI: DOM slot sizes and starting font sizes (--budget)
scripts/review_sheet.py   CLI: 720px review thumbnails + a 2×2 contact sheet (4 cards at a glance)
scripts/validate.py       CLI: spec gate (structural violations + geometry wall + notices)
scripts/render.py         CLI: HTML → PNG (browser detection)
scripts/measure.py        real-browser text measurement (pixel + content gates)
scripts/pipeline.py       build → measure → fix loop → render, up to 3 rounds
scripts/doctor.py         environment self-check
scripts/vision_probe.py   one-shot check of whether the current model can really read images
templates/contracts.yaml  per-layout character budgets (the contract)
examples/                 5 complete specs (both .json and .yaml)
docs/                     manuals: layouts, contracts, rendering, troubleshooting, extending
docs/images/showcase/     the real run shown in this README
install.ps1 / install.sh  one-line installers (clone + environment check + doctor), agent-driven
```

---

## 📄 License

MIT for the code. The bundled font (**ZCOOL KuaiLe / 站酷快乐体**) is under the
[SIL Open Font License 1.1](assets/fonts/OFL.txt) — see [LICENSE](LICENSE) for the split.
That font is the only third-party asset in the repository.