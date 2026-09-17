# text-to-infographic

> **Turn a long article into a ready-to-publish 3:4 card carousel** — a cover plus one page per key
> point, hand-drawn card style. You hand it the article; the scripts own every pixel.

[中文说明](README.md) · [SKILL.md](SKILL.md) · [docs/](docs/)

Text is always crisp (never garbled the way image generation renders CJK), every page stays
hand-editable, and the same spec always renders the same set of images — byte for byte.
The model writes copy inside a declared character budget; fonts, spacing, strokes and colors are
decided by code:

```
article.md ──> [LLM] spec.json ──> validate ──> build ──> measure (real browser) ──> PNG × N
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
| Derives the page count from the formula (cover + sections, thin sections paired up) | SKILL.md step 2 |
| Both gates must pass; `needs_llm` means shortening copy and re-running, never skipping | SKILL.md steps 4–5 |
| **Looks at every card**: broken words, orphan lines, truncation, overlap, mismatched counts | SKILL.md step 6 |
| Reports the gate output **verbatim** + page-count reasoning + self-check result + leftovers | SKILL.md step 6 |

Output is `card-01.png …`, 2160×2880 by default (3:4 @2x; `render.py --scale 1` gives 1080×1440).

### 3 · Or drive it yourself (if you want to change the code)

```bash
git clone https://github.com/Chendestiny/text-to-infographic
cd text-to-infographic
python scripts/validate.py spec/my-deck.json                    # spec gate: per-slot character budgets
python scripts/pipeline.py spec/my-deck.json -o out/my-deck     # build -> measure -> render
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

**Recommended range: 6–9 cards** (Xiaohongshu's own spec allows 1–18 and recommends 6–9). The count
comes from how you *cut* the article, **not from its length**: cards ≈ 1 (cover) + sections, pairing
two sections per card when a section averages under 400 characters, and compressing to 4–5 cards
below 1.5k characters. A 228-line article becomes 7 cards; a 1000-line one becomes 8–10.

| article size | cards (cover included) | how it is carried |
|---|---|---|
| ≤1.5k chars / 1–2 sections | 4–5 | one point per card |
| 1.5k–3k / 2–3 sections | 5–6 | one section per card |
| 3k–6k / 4–6 sections | 6–8 | 1–2 sections per card; merge the pitfalls into one `bullets` card |
| 6k–10k / 6–10 sections | 8–12 | one theme per card (`meta.max_cards` declares the budget) |
| >10k / 10+ sections | **split into a series**, 6–8 cards each | never cram 18 cards into one post |

Density is carried by the layouts (one `bullets` card holds 4–6 rows, one `chain` walks 5–6 steps,
one `compare` is a 4+4 table) — that is what keeps the count down. `validate.py` reports in tiers:
over budget is a soft notice, over the platform limit of 18 is a hard violation.

---

## 🧭 How it stays correct: two gates, three checks

Every layout declares a **character budget for every text slot** in
[templates/contracts.yaml](templates/contracts.yaml), measured from renders that actually look good —
not guessed. Copy is written *inside* that budget instead of hoping it fits.

| gate | what it is | catches |
|---|---|---|
| **spec gate** `validate.py` | pure string math, milliseconds, zero tokens | copy over budget, reported by exact path: `card-03(chain).steps[1].text  17.5 > max 15` |
| **pixel gate** `measure.py` | renders in a real browser and reads **actual text bounding boxes** via `getBBox()` | real width overflow, text past the canvas, text spilling out of its box, HTML rows breaking the card bottom |
| **content gate** (inside the pixel gate) | every string the spec registered must actually appear in the render | text that is neither overflowing nor clipped but simply **never drawn**, plus tails the engine replaced with an ellipsis |

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
scripts/ink.py            rendering core: hand-drawn primitives + 13 layouts + page assembly
scripts/decor.py          decoration parts (gears / stars, pure SVG)
scripts/build.py          CLI: spec → HTML
scripts/validate.py       CLI: character contracts (spec gate) + page-count range notice
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