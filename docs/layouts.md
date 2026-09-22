# 版式参考（15 种）

每个版式的**全部可用字段**、字数预算、以及什么时候该用。

> **皮肤和版式是两件事**：版式决定"哪里放什么"，皮肤（`meta.theme`）决定"长什么样"。
> 15 个版式 × 每套皮肤任意组合，**版式字段一个都不用改**。皮肤清单与挑选方式见
> [style.md](../assets/style.md#主题皮肤) 与 `python make_theme_gallery.py --family paper`。

**文字排版**：每种版式的文字都是 DOM（浏览器折行 + 垂直居中 + 自动缩字号），引擎只给「容器的矩形」。所以下面的字数预算只是**写作建议**，真放不下时**浏览器会缩字号**（autofit，缩到槽内），缩到下限仍放不下才在报告里点名。

**字数口径**：汉字 = 1；**其他一切（字母 / 数字 / 空格 / 换行 / 符号）= 0.5**；
**全角标点（，。：、「」——）算 1**（码位 > U+2E80，跟汉字同档）；`[[高亮]]` 标记本身不计。
`\n` 也按 0.5 计，所以换行不是免费的。拿不准就现算：
`python scripts/validate.py --count "一段文案"`。
预算的机器可读版本在 [../templates/contracts.yaml](../templates/contracts.yaml)，这里是给人看的。

**字段支持总表** —— 规格里写了引擎不读的字段，以前会**静默消失**（三道门一起失明），
现在规格门会拦；但先知道更省事：

| 字段 | 支持 | 写了不渲染（规格门报违规） |
|---|---|---|
| `note` | arch / chain / cover / **cover_title** / **cover_quote** / flow / hub / matrix / pyramid / spectrum / timeline | **bullets / compare / cycle / raw** |
| `note2`、`mid` | 仅 `flow` | 其余全部 |
| `dashed` + `dashed_label` | `chain` / `flow` | 其余全部 |
| `gradient`（两端色） | 仅 `spectrum` | 其余全部 |
| `kicker` | **cover_title** / **cover_quote** | 其余全部 |
| `accent`、`quote`、`source` | **cover_title**（`accent`）/ **cover_quote**（`quote` / `source`） | 其余全部 |

> 别按文档猜字段能不能渲染——文档可能落后于代码。最快的验证：
> `grep 'card.get("字段名")' scripts/ink.py`；有命中才是真的渲染。

样张一张看全：[images/layouts/版式图鉴.png](images/layouts/版式图鉴.png)
（`python make_layout_gallery.py` 重新生成 —— 它同时是"每个版式都能渲染"的回归证据）。

---

> **文字排版已改为 DOM**：折行 / 行数上限 / 垂直居中 / 字号自适应都由浏览器负责，引擎只给槽的矩形。本文中若出现 `wrap_text` / `fit` / `密集档` / `textLength` 等提法，属于**迁移前的历史机制**，现已删除或不再参与判定；详见 [architecture.md 的《文字排版：为什么是 DOM》](architecture.md)。

## cover — 汇总封面（四宫格）

**只用于第一页。** 文档标题由页头统一渲染，下面是 **2×2 四宫格**，
每格一个「微缩版式」，自己带彩色小标题标签。

设计意图：读者拿到一套图，最先想知道"这套图讲了什么"。四宫格把四个要点各用
一个缩小版版式铺出来，等于**把目录做成了封面**。

| 字段 | 类型 | 预算 | 说明 |
|---|---|---|---|
| `title` | str | 4–30（最多 2 行） | 文档标题；写 `\n` 指定断行 |
| `subtitle` | str | ≤22 | 副标题 |
| `note` | str | ≤44（软） | 底部一行 |
| `quads` | list | **2–4 个**（不足则留空） | 每格一个模块 |
| `quads[].label` | str | ≤10 | 模块小标题，**自动带彩色标签** |
| `quads[].mini` | str | — | 微缩版式：`list` / `boxes` / `nested` / `steps` |
| `quads[].items` | list | 1–4 项 | `{text, desc}`，`text` ≤12、`desc` ≤12（软） |
| `quads[].line` | str | ≤14 | 仅 `boxes` / `steps` 用：底部一行说明 |
| `quads[].chips` | list[str] | 2–4 个，每个 ≤6 | 仅 `nested` 用：底部一排小标签 |
| `quads[].fs` / `fs2` | int | — | 需要时手动指定字号（不常用） |

### 四种微缩版式怎么选

| mini | 长什么样 | 适合 |
|---|---|---|
| `list` | 每行一个勾 + 文字（行可上色） | 要点罗列、特点清单 |
| `boxes` | 2~3 个并列方框（可带底部一行） | 并列概念、三档取舍 |
| `nested` | 大框内嵌 2 个小框（可带底部 chips） | 分层结构、角色分工 |
| `steps` | 3~4 个横排小块 + 箭头 | 流程、循环 |

> ⚠ **微缩格子里优先用中文短词**：格子只有约 130px 宽，`Observation` 这种拉丁长词
> 放不下只能从中间折断。参考图里用的全是中文短词，也是这个原因。

```json
{"layout": "cover",
 "title": "Agent + ReAct 循环 + Workflow",
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
    "items": [{"text": "会自己拆步骤"}, {"text": "会调用工具"}]},
   {"label": "速记总结", "mini": "boxes",
    "items": [{"text": "固定流程"}, {"text": "部分决策"}, {"text": "自主任务"}],
    "line": "越往右越需要 Agent"}]}
```

## cover_title — 大字标题封面（纯文字）

**一句话占满整页。** 参照的是小红书最常见的那种封面：**左对齐、一行一个词组、
其中一行下面压一条粗色条**。和 `cover`（四宫格）是两个方向 —— 四宫格是"目录"，
这个是"标题"。

它**不走页头**（标题由版式自己画），所以字号上限比普通页的 `h1` 更大（124px）。

| 字段 | 类型 | 预算 | 说明 |
|---|---|---|---|
| `title` | str | 4–26（最多 4 行） | 主标题，**必须用 `\n` 手动断行** |
| `accent` | int | 1–2 | 第几行压色条（1 起），默认 2；只有一行时默认 1 |
| `kicker` | str | ≤10 | 左上角小标签（用主题强调色） |
| `subtitle` | str | ≤16 | 标题下方的支撑句（一行，左对齐） |
| `note` | str | ≤30（软） | 最底部小字 |

> ⚠ **不要靠自动折行**。封面最忌词组被切散 —— 想要哪里断就写 `\n`。
> 字号按"最长一行必须放得下"反解，写 4 行时会自动缩到最长那行刚好排满。

```json
{"layout": "cover_title",
 "title": "Qoder和Zcode\n二选一\n哪个更适合大肥鱼\nv4.1flash",
 "kicker": "AI 编程工具", "subtitle": "两条路线实测对比", "note": "看完就知道选谁"}
```

## cover_quote — 金句封面（结论先行）

把整篇最锋利的那句话单独占一页。和 `cover_title` 的区别是**居中**排版，
上下各一条短色条把它框成一块。

| 字段 | 类型 | 预算 | 说明 |
|---|---|---|---|
| `quote` | str | 6–44 | 金句正文，可写 `[[关键词]]`；整句**最多排 4 行**（自动折行） |
| `title` | str | ≤44 | `quote` 的别名（二选一，先读 `quote`） |
| `source` | str | ≤16 | 出处 / 作者，自动加破折号 |
| `kicker` | str | ≤10 | 左上角小标签 |
| `note` | str | ≤30（软） | 最底部小字 |

```json
{"layout": "cover_quote",
 "quote": "窗口是工作台，不是仓库", "source": "长任务那一章的结论",
 "kicker": "一句话记住"}
```

> `quote` 是**一个槽**，折行完全交给浏览器 —— 手工折行会在不同字号下断错地方。

## hub — 中心圆 + 并列概念框

原来的封面版式，**现在是独立版式，任何页都能用**（比如讲"三件套"那一页）。
≤3 个概念横排 + 箭头指向中心圆；>3 个自动转竖排列表。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` / `subtitle` | str | ≤14 / ≤20 |
| `hub` | str | ≤6（中心圆里的字） |
| `items` | list | 2–6 项，`{big, en, tag, color}` |
| `items[].big` | str | ≤6 |
| `items[].en` | str | ≤18（放不下自动拆两行） |
| `items[].tag` | str | ≤6 |
| `note` | str | ≤44（软） |

> 竖排形态（>3 个）用 `text` 字段：`{text: "① [[摆对东西]]：窗口里放什么"}`

## chain — 竖向步骤链

**最常用。** 流程、步骤、回路。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` / `subtitle` | str | ≤14 / ≤22 |
| `steps` | list | 3–6 项，每项 `{text, fill}` |
| `steps[].text` | str | 5–15 |
| `steps[].fill` | str | 上色；**不写自动全上色轮换**，写 `none` 才留白 |
| `note` | str | ≤44（软） |
| `dashed` / `dashed_label` | bool / str | 加虚线容器框，标签 ≤12 |

## cycle — 环形循环

循环类内容（ReAct / PDCA）。节点围成一圈，弧形箭头顺时针连。
**关键词链的字号由最长词决定，四个词一样大。**

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` / `subtitle` | str | ≤14 / ≤22 |
| `keywords` | list[str] | 3–4 个，每个 ≤8 |
| `nodes` | list | 3–6 项，`{text, desc, fill}` |
| `nodes[].text` | str | ≤8 |
| `nodes[].desc` | str | ≤22（软） |

## spectrum — A→B 单步骤详情

渐变粗箭头从 A 指到 B，下面列细节。**适合"两个极端之间的取舍"**。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` | str | 3–26（最多 2 行） |
| `subtitle` | str | ≤22 |
| `stages` | list[str] | 2–4 个，每个 ≤7，用 ` → ` 连起来显示 |
| `ends` | list[str] | **恰好 2 个**，每个 ≤9（箭头两端标签） |
| `items` | list | 3–5 项，`{text}`，每项 6–16 |
| `gradient` | list[(色, 位置)] | 可选；默认 `#8A9096 → #7FCBEF → #F79BB0 → #8A9096`，
**两端刻意用中灰而不是黑**（黑色端点实测不好看） |

## timeline — 纵向时间轴

竖轴**水平居中**，节点文字左右轮流分布。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` / `subtitle` | str | ≤14 / ≤22 |
| `steps` | list | 3–6 项，`{text, desc, fill}` |
| `steps[].text` | str | 3–10 |
| `steps[].desc` | str | ≤30（软） |

## flow — 横向节点链

链路、数据流。可选底部再放一排小框填补留白。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` / `subtitle` | str | ≤14 / ≤22 |
| `mid` | str | ≤14（顶部灰色说明） |
| `nodes` | list | **3–4 项**（>4 请改用 `chain` / `bullets`），`{text, desc, fill}` |
| `nodes[].text` | str | ≤7 |
| `nodes[].desc` | str | ≤18（软） |
| `bottom` | list | 可选，2–4 项，`{text, desc, fill}`；`text` ≤6、`desc` ≤16（软） |
| `note` / `note2` | str | ≤44（软） |
| `dashed` / `dashed_label` | bool / str | 虚线容器（标签**画在框内顶部**） |

## bullets — 清单

坑、注意事项。**行高由浏览器分配**（不是算出来的），条数越多字号越小。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` / `subtitle` | str | ≤14 / ≤22 |
| `items` | list | **2–6 项**，`{no, head, desc, fill}` |
| `items[].no` | str | 序号，如 `"①"`，可省 |
| `items[].head` | str | ≤12 |
| `items[].desc` | str | ≤34（软） |

> ⚠ 超过 6 条就别硬塞：字号会被压到不可读。拆成两页，或改用 `timeline`。

## compare — 左右两列对照

反例 vs 正解、改造前后。**两个外框不填色，内层块按数量自适应高度填满外框。**

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` | str | 3–16 |
| `subtitle` | str | ≤22 |
| `left` / `right` | obj | 各含 `label` / `blocks` / `note` |
| `.label` | str | ≤10，支持 `[[高亮]]` |
| `.blocks` | list | 2–5 项；可以是纯字符串，或 `{text, fill}` |
| `.blocks[].text` | str | ≤12 |
| `.note` | str | ≤44（软） |

## matrix — 2×2 四象限

按规模/维度选型。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` | str | 3–16 |
| `subtitle` | str | ≤22 |
| `labels.top` / `labels.left` | str | ≤10（轴标签，可省） |
| `cells` | list | **恰好 4 个**，`{head, desc, fill}` |
| `cells[].head` | str | ≤8 |
| `cells[].desc` | str | ≤32（软） |
| `note` | str | ≤44（软） |

## pyramid — 金字塔

分层结构：从塔尖到基座逐层变宽。适合能力层级、优先级分层、抽象到具体。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` / `subtitle` | str | ≤16 / ≤22 |
| `levels` | list | **2–6 层**，`{text, desc, fill}` |
| `levels[].text` | str | ≤10 |
| `levels[].desc` | str | ≤14（软） |
| `note` | str | ≤44（软） |
| `fs` | int | 可选，手动指定层内字号 |

> **数组顺序 = 从上到下**：第 1 个在塔尖（最窄），最后一个在基座（最宽）。
> 每层是**梯形**（层与层之间宽度连续）——方框堆叠看起来是条形图，斜边才是金字塔的视觉信号。

```json
{"layout": "pyramid", "title": "Agent 能力金字塔",
 "subtitle": "越往上越需要[[自主决策]]",
 "note": "底座不稳，上层就是幻觉",
 "levels": [
   {"text": "自主规划", "desc": "自己决定做什么"},
   {"text": "工具编排", "desc": "串多个工具"},
   {"text": "单工具调用"},
   {"text": "提示词工程"},
   {"text": "基础模型能力"}]}
```

## arch — 结构图

角色/结构/三件套：大框内嵌子框 → 箭头 → 一个框，底部一排 chip。

| 字段 | 类型 | 预算 |
|---|---|---|
| `title` / `subtitle` | str | ≤14 / ≤22 |
| `host_label` | str | ≤10（大框标题） |
| `host_fill` | str | 可选（大框默认不填色） |
| `inner` | list | 1–2 项，`{text, desc, fill}`；`text` ≤6、`desc` ≤8 |
| `link_label` | str | ≤6（箭头上的小字） |
| `server` / `server_desc` / `server_fill` | str | ≤8 / ≤10 / 颜色 |
| `line` | str | ≤16（中间那行强调，支持 `[[高亮]]`） |
| `chips` | list | 2–4 项，`{text, desc, fill}`；各 ≤6 |
| `note` | str | ≤44（软） |

## raw — 逃生舱

直接给一段 SVG。**规格表达不了的特殊页才用**，因为页面高度要自己算，
画到画布外会被静默裁掉。

```json
{ "layout": "raw", "svg": "<svg class='stage' width='824' height='900' ...>...</svg>" }
```

---

## 怎么选（决策顺序）

1. **第 1 页** → `cover`（四宫格汇总）；只想放标题 + 几个概念就用 `hub`
2. **有先后顺序** → `chain`（竖向、步骤多）/ `timeline`（有阶段感）/ `flow`（横向链路、想同时展示上下游）
3. **会回到起点** → `cycle`
4. **两个极端之间取舍** → `spectrum`
5. **并列但要对比** → `compare`
6. **并列不对比、只是列举** → `bullets`
7. **按两个维度分类** → `matrix`
8. **有"容器/角色"关系** → `arch`
9. **有层级/优先级** → `pyramid`（从塔尖到基座）
9. 以上都不合适 → `raw`
