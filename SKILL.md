---
name: text-to-infographic
description: >-
  Turn a long article into ready-to-publish Xiaohongshu / Instagram carousel cards — a cover plus
  one page per key point, 3:4 vertical, hand-drawn card style. Deterministic rendering, NOT AI
  image generation: the text stays crisp, the same spec always yields the same deck, and every page
  remains hand-editable. 把长文/文章转成小红书竖版图文：封面 + 每页一个要点，脚本渲染、可复现、可手改。
version: 1.0.0
---

# text-to-infographic（Agent 手册）

> 一篇长文 → 一套直接能发的小红书图文。你**只出规格、不碰像素**：字号 / 留白 / 描边 / 配色
> 全由 `scripts/ink.py` 决定，所以同一份规格永远出同一套图，每一页都能手改。

**全部工具面就是 `run.py` 一条命令，四种用法**（先看这张表，细节按需查）：

**别分头跑**（实测：分头跑 validate/pipeline/preflight/capacity 会让一轮多出
20+ 次调用，全花在"自己拼输出"上）：

| 什么时候用 | 命令 |
|---|---|
| ① 决定拆几页（**只跑一次**） | `python scripts/run.py --plan <文章.md>` → 页数 + 区间 + 每页骨架 + 可直接粘贴的 `meta.plan` |
| ② 写规格阶段 | `python scripts/run.py <spec.json> --budget --no-render` → 每槽字数预算 + 预检 + 规格门 |
| ③ 交付 | `python scripts/run.py <spec.json> --article <文章.md> --out <出图目录>` → 预检 + 页数对账 + 规格门 + 像素门/几何门 + 出图 + 复核缩略图 + **一句结论** |
| ④ **单页返工** | `python scripts/run.py <spec.json> --only 5 --out <出图目录>` → 只重建第 5 页，**1~2 秒**，其余页原样不动 |
| ⑤ 换皮肤 | 加 `--theme <key>`（3~5 都能用）；不写就用规格里的 `meta.theme`，再没有就是 `crayon` |

**四道门全在 `run.py` 里**（文字预检 / 规格门 / 像素门 + 几何布局门 / 内容门）。
**不要在 run.py 之外单独跑 plan.py / validate.py / pipeline.py / preflight.py** —— 它们的结果
全都已经并在 run.py 的结论里，重复跑只是多烧时间。

### 卡壳与失败怎么兜（别自己写 try，也别死等）

- **每道门都有超时**：超时会明说 `✗ pipeline.py 超时（600s，已强制中止）` 并退出，
  **不会挂死**。做法是先重跑同一条命令；反复超时再查环境（`python scripts/doctor.py`）。
- **像素门崩溃/超时会自动重试 1 次** —— 浏览器冷启动慢、profile 被占这类抖动占大多数。
- **渲染失败不再被吞**：哪张没出图会点名（`✗ 以下页没有出图：card-03`），退出码非零。
  **其余已出好的图会保留** —— 不会因一张失败把整套删掉。
- 慢机器上放宽：`T2I_TIMEOUT_SCALE=2 python scripts/run.py ...`（所有超时按比例放大）。

### ④ 单页返工（人在回路）

用户说「第 5 张不行，重做」时：**只改规格里 card-05 那一段**，然后

```bash
python scripts/run.py <spec.json> --only 5 --out <出图目录>
```

只重建 + 重测 + 重出第 5 页，**1~2 秒**，其余页的 HTML 与 PNG 一字不动。
**不要**为一张图重跑整套 —— 既慢（整套 ~15s vs 单页 ~1s），
又可能让其它页因为 calib 微调而长得和原来不完全一样。

---

## 一、五步流程

**第 1 步 · 环境**：`python scripts/doctor.py`
（Windows 上 `python` 不在 PATH 就用 `py -3`）。doctor 提示"只有 CDP 后端可用"时先设
`$env:T2I_BACKEND='cdp'`，否则截图会全是 0 字节。

> ⚠ **顺手确认 `python -c "import yaml"` 不报错**。规格门要拿 pyyaml 解析契约本体
> `templates/contracts.yaml`，**与规格是不是 `.json` 无关**。缺了它规格门会直接跑不起来
> （现在会被判成硬问题并说清楚，不要再当成"有提示"跳过）。缺就 `pip install pyyaml`。

**第 2 步 · 切页：跑脚本，别自己推**
```bash
python scripts/run.py --plan <文章.md>
```
它输出：汉字数 / 节数 / 每节字数 → **建议张数 + 允许区间 + 每页骨架**。
区间 **4~9 张**（6~9 是小红书平台偏好区，平台上限 18，超过 12 该拆系列）。
张数 ≈ 1（封面）+ 章节数；平均每节 <400 汉字两节并一页；全篇 <1.5k 汉字压到 4~5 张 ——
这些 `--plan` 都替你算完并写出了推导。
**页数由"切法"决定，不随行数增长**：228 行是 7 张，1000 行也是 8~9 张，永远不是 100 张。
写完规格**拿脚本对一次账**（张数是硬数字，不是你发挥的地方）：

```bash
python scripts/run.py <spec.json> --article <文章.md> --no-render
```

（交付时给了 `--article` 也会自动做这一步；这里只是想早点看到结果。）
把 `--plan` 打印的 `"plan": {...}` 原样复制进规格的 `meta`。门禁按它判页数：
**建议值或区间内 = 通过；最多上浮 1 张且要写 `meta.plan.note`；超过上沿 +1 = 硬违规**
（默认动作是**合并相邻页**，不是写理由）。细节见 [docs/contracts.md](docs/contracts.md)。


**第 3 步 · 写规格**：从 [examples/](examples/) 抄一个形状再改文案。
**先把骨架写成规格（版式与条数定了、文案留空）跑一次**：
`python scripts/run.py <骨架.json> --budget --no-render` —— 一眼看到每槽能放几个汉字 + 预检结论。
实测这一步能把 4 轮返工压到 1 轮；**文字放不下由浏览器自动缩字号兜住（autofit），不用为它反复改文案**。


- 版式字段表在 [docs/layouts.md](docs/layouts.md)，开头还有一张**字段支持总表**
  （`note` 在 bullets / compare / cycle / raw 上写了也不渲染，规格门会拦）
- **字数上限只是写作建议**：真实能不能放下由**浏览器实测**说话（`run.py` 的 DOM 槽检查）。拿不准就跑 `--budget`
- 放不下时**先换版式或换写法**（一页 `bullets` 4~6 条、`chain` 5~6 步、`compare` 4+4 条），别硬塞
- 语法见本文「三、规格语法」

**第 4 步 · 交付：跑一条命令**
```bash
python scripts/run.py <spec.json> --article <文章.md> --out <出图目录>
```

它一次做完：文字预检 → 页数对账 → 规格门 → 像素门/几何门 → 出图 → 复核缩略图 → 一句结论。

- **只看结论里的「必须改」**：逐条改掉再跑同一条命令，通常 1~2 次就干净
- 「引擎自己兜住的妥协」**不是你的活**：文字折行、行数上限（`-webkit-line-clamp`）、垂直居中、
  字号自适应都交给浏览器；字小一点不是问题，**不要为它反复改文案**（实测那样会多烧 3~4 轮、几分钟）
- 真正会把 LLM 拉回来只有两类：**`dom-overflow`**（浏览器缩到下限仍放不下 → 改短文案）
  和**页数超硬上限**（合并相邻页）。`dom-orphan`（末行只剩 1~2 字）是提示，能改就改

`run.py` 的输出一眼能看：`① 预检 ② 页数 ③ 规格门 ④ 像素门 ⑤ 复核图`，最后一段是结论。
其中 `④ 像素门` 里 `measure: N 处溢出 / verify:` 是真实浏览器实测的结果。

**第 5 步 ·（可选）看一眼观感**
正确性四道门已经量完了，这一步只判**配色与疏密**这种主观项，**默认可以不做**。
要做就只看 1 张（封面），把这张图交给看图模型并照抄这句（不说这句它会写整段图像描述，40~115 秒）：

> 只看三点，每点一行，不要描述图片：1) 有没有文字压在框线或箭头上？2) 有没有两段文字叠在一起？3) 配色是否协调？

没有 vision provider 就直接跳过，报告里写「审美未校验」——别去折腾 harness 配置。


---

## 二、编排分工（多篇 / 多页怎么并行）

| 环节 | 谁做 | 能并行吗 |
|---|---|---|
| 切页 + 页骨架 | `run.py --plan`（脚本） | 答案已经算好，不用模型推 |
| 写规格 | 你，或一个文案 subagent（输入 = 文章 + 骨架 + 字段表） | **能**：一篇 = 一个单元 |
| 过门 + 渲染 + 出图 | `run.py`（纯脚本，0 token） | 能但没必要（0.5s/页） |
| 逐张复核 | 看图 subagent（只报上面四类） | **能**：一次复核分 2~3 片 |

同一篇内部（写规格 → 过门 → 渲染 → 复核 → 返工）**必须串行**，有依赖。
**并发上限 2~3**：每个 subagent 一份独立上下文，每个渲染还要拉一个 Chrome。

---

## 三、规格语法

```json
{ "meta": { "theme": "crayon", "footer": "", "frame": ["pen", "card", "none"],
            "decor": true,
            "plan": { "suggest": 4, "range": [4, 5],
                      "note": "偏离理由（一致就不用写）：骨架 card-03 装不下第二章 15 个组件" } },
  "cards": [
    { "layout": "chain",
      "title": "Function Calling",
      "subtitle": "[[tool_call]] 是模型吐的，干活的是代码",
      "steps": [
        { "text": "① 注入 [[tools 定义]]" },
        { "text": "③ 模型返回 tool_calls", "fill": "yellow" }
      ],
      "note": "回到 ② 步，直到模型不再调工具" }
  ] }
```

- **`meta.theme`（或 `--theme`）换皮肤**（默认 `crayon` 蜡笔纸感）。皮肤分**两个族**：
  - **纸张族**（复用现有版式）：`crayon` 蜡笔纸感 / `grid` 方格稿纸 / `retro` 复古报刊
  - **工程族**（节点画法不同；版式仍在调整，但已可交付）：
    `terminal` 暗夜终端 / `blueprint` 工程蓝图 / `mono` 素白细线 / `nord` 北欧冷调

  **版式字段、字数、四道门口径完全一样**，只换皮。不确定选哪套就先跑
  `python make_theme_gallery.py --family paper`（出图到桌面 `t2i-themes/`，加 `--family diagram` 看工程族）。
  名字写错会当场报错，**不会静默回落**。
- `meta.frame` 每页轮换：`pen` 手绘框 / `card` 圆角卡 / `none` 无框（不给就跟皮肤走）；
  `meta.decor` 控制装饰
- 标题里写 `\n` 可显式断行；单卡可覆盖 `frame`；chain / flow 支持 `dashed` + `dashed_label`
- **高亮**：`[[关键词]]` 自动轮换色，`[[x|b]]` 指定色
  （`b` 蓝 / `y` 黄 / `p` 粉 / `g` 灰 / `gr` 绿 / `o` 橙）。
  轮换起点与顺序由皮肤给，所以同一段文案在不同皮肤下的高亮配色不同
- **上色**：方框默认全部上色、颜色自动轮换；想让某框留白表示"这步不重要"写 `"fill": "none"`；
  框已上色时框内文字不再画色带，且**文字色自动按底色亮度反差**（引擎行为，不用处理）
- **封面**：`cover`（四宫格目录）/ `cover_title`（大字纯文字标题，`\n` 手动断行）/
  `cover_quote`（金句，居中）。第一张最值钱，三选一，详情见 [docs/layouts.md](docs/layouts.md)

---

## 四、环境与能力

- Python 3.8+（核心脚本只用标准库）；**`.json` 规格零第三方依赖**，`.yaml` 需要 pyyaml
- 渲染需要 Chromium 系浏览器（Chrome / Edge，`doctor.py` 自动识别）；字体已内置
- Windows 上 `python` 不在 PATH 就用 `py -3`
- **能不能读图必须实测**，不能靠"harness 声明"：`python scripts/vision_probe.py` 读出那张探针图，
  答对"背景色 + 中间形状"才算能读；请求成功但说不出具体内容 = **静默丢图**，按不能读处理。
  判定不通过时只能说"正确性由脚本实测保证、审美未校验"，**不许写"视觉已检查"**。

---

## 五、出问题去哪查

| 症状 | 读哪 |
|---|---|
| 页数 / 密度拿不准 | 本文第 2 步 + `run.py --plan` 的输出 |
| 报 `dom-overflow` / `dom-orphan` | [docs/troubleshooting.md](docs/troubleshooting.md) |
| 报未知字段 / note 不渲染 | [docs/troubleshooting.md](docs/troubleshooting.md) |
| 不知道某版式有哪些字段 | [docs/layouts.md](docs/layouts.md)（含字段支持总表） |
| 截图 0 字节 / 后端问题 / profile 冲突 | [docs/rendering.md](docs/rendering.md) |
| 想看"为什么这么设计" | [docs/architecture.md](docs/architecture.md) |
| 想加一种版式 | [docs/extending.md](docs/extending.md) |
| 交付前过一遍 | 下面这份清单 |

---

## 六、交付检查清单

一条 `run.py <spec.json> --article <文章.md> --out <目录>` 跑完，看它的结论段就够：

- [ ] ① 预检：数量词与规格里实际的条数一致（孤字 / 断词已移到浏览器侧，由 `dom-orphan` 报）
- [ ] ② 页数：落在 `run.py --plan` 给的区间内（4~9）
- [ ] ③ 规格门：**0 硬违规**（结构 + 几何墙）
- [ ] ④ 像素门：0 溢出、无 `crosses-*` / `overlap`，降级报告无遗漏
- [ ] 结论段是「✓ 硬问题 0 处」；若有 `needs_llm`，只可能是 `dom-overflow` 或结构问题
- [ ] **每一页都真的有图**：`card-01..N.png` 一个不少（run.py 会独立数一遍文件，
      不信任上游报告）。缺哪张就改规格里那一段后 `--only N` 单独返工
- [ ] 交付时给了门禁逐字输出 + 页数理由 + 降级报告 + 自检结论
- [ ] 产物：`card-01..N.png`，默认 2160×2880（3:4 的 2 倍图）。
      要调风格改 `assets/style.md` 里的常量，**不要**改单页 HTML —— 一页一改风格就飘了