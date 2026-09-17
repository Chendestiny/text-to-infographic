# 版式参考（13 种）

每个版式的**全部可用字段**、字数预算、以及什么时候该用。
字数口径：**汉字 = 1，其他字符（字母/数字/空格/符号）= 0.5**；
`[[高亮]]` 标记本身不计字数。预算的机器可读版本在
[../templates/contracts.yaml](../templates/contracts.yaml)，这里是给人看的。

样张见 [../docs/images/layouts/](images/layouts/)。

---

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
| `nodes` | list | 3–5 项，`{text, desc, fill}` |
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
