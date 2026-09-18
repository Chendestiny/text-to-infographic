# 架构

## 一句话

**LLM 只负责"读懂文章 + 在字数预算内总结"，像素决策全部由脚本承担，
中间用机器可校验的契约连接。**

## 为什么不直接让 LLM 写 HTML

| 做法 | 结果 |
|---|---|
| AI 生图（扩散模型） | 文字必糊，中文尤甚，标题都拼不对 |
| 让 LLM 写 HTML/SVG | 每次都长得不一样：间距、字号、框位置都是新的；风格无法维护、结果无法复现、单页无法手改 |
| 让 LLM 写 HTML + 固定模板 | 结构对了，但**文案长度不可控** → 文字溢出框；改好一版换个题材又崩 |

第三条是最隐蔽的：问题不在 LLM 写得好不好，而在**约束从未被声明**。
所以本项目的核心不是模板，是**把容量写成契约**。

## 流水线

```
文章.md
  │
  ├─[LLM]─> spec.json ─────────────────────────────── 唯一需要模型的一步
  │            │
  │            ├─ validate.py ──── 规格门（字数契约，纯脚本，零 token）
  │            │      └ 违规 → 报精确路径 → LLM 改那一条 → 重跑
  │            │
  │            └─ pipeline.py
  │                   ├─ build.py          规格 → HTML（ink.py 渲染）
  │                   ├─ measure.py        像素门：真实浏览器 getBBox 量文本
  │                   ├─ verify            溢出分流
  │                   │     ├ 宽度类 → autofix（校准估算器 + textLength）→ 回 build（≤3 轮）
  │                   │     └ 内容/版式类 → needs_llm 清单 → 直接交回 LLM（不空转轮次）
  │                   └─ render.py         HTML → PNG
  └─────────────────────────────────────────────────> out/card-01..N.png
```

`pipeline.py` 是 LangGraph 风格的状态机（State / Node / Conditional Edge），
但**不依赖 langgraph 包**——节点就是函数，状态就是一个 dict。需要时可以平移。

## 两道门为什么都要有

| 门 | 成本 | 抓什么 | 漏什么 |
|---|---|---|---|
| 规格门 `validate.py` | 毫秒级（含一次无浏览器渲染算几何） | 结构问题 + **几何放不下**（丢字 / 缩到不可读） | 真实字体度量偏差（由像素门兜） |
| 像素门 + 几何布局门 `measure.py` | 每页一次无头浏览器（`getBBox` 量宽 + `getBoundingClientRect` 量位置） | 溢出、越界、文字互相压住、压线、穿框 | 配色与疏密这类主观项 |

**能机械校验的绝不交给模型判断。** 两道门都是纯脚本，不花 token；
只有像素门把某几条升级成 `needs_llm` 时，模型才回来改文案。

### 像素门里还包着一道「内容门」

渲染时每个文字槽位都会把**净文本**登记下来（`ink._reg_text` → `_TEXTS` →
埋进 HTML 的 `<!--T2I_TEXTS:[...]-->`）；`measure.py` 取卡片的 `textContent`
逐条核对，缺失的报 `missing-text`。

★ 多行文本（`txt_block`）登记的是**折行前的原文**，不是渲染出来的行。这点很关键：
只登记"渲染出来的行"的话，引擎把长文案折算成「…」时两边都是半句话，门永远发现不了断尾
（真实事故：timeline 节点说明的后半句被吃掉，门报"干净"，靠外部复核肉眼才发现）。

它防的是**静默吞字**：文字没画出来时，既不溢出也不压框，**几何检查永远发现不了**。
真实事故：`_inline()` 漏掉了最后一个 `[[高亮]]` 之后的尾巴，导致
「完全没有 `[[高亮]]` 的副标题整条变空」——5 份示例、42 张图全部通过，
是外部 agent 拿真实文章跑时肉眼发现的。这道门就是那次事故的产物。

## 校准闭环（为什么第 2 轮起就准）

`tw()` 是宽度**估算器**（汉字 1em、其余 0.62em）。字体度量估不准：
拉丁偏宽、bold 加粗、letter-spacing 都是变量——估不准就会出现
"build 说没问题、图上文字出框"。

所以 `measure.py` 把**真实宽 / 估算宽**的比值回写成 `ink.CALIB`，
`tw()` 乘上它。估算器自己越跑越准，这就是为什么大多数规格**第 1 轮就干净**、
而剩下的也能在第 2 轮收敛。

对仍溢出的单行文本，autofix 直接注入 SVG 的 `textLength` + `lengthAdjust=spacingAndGlyphs`
（等比压缩字形和字距），保证压回框内。

## LLM 的位置（两处，都在明处）

1. **事前**：读文章 → 决定拆几页（区间 4~9 张，唯一定义在 [../SKILL.md](../SKILL.md) 第 2 步）→ 选版式 → 在契约字数内写文案
2. **事后**：像素门报 `needs_llm` 清单 → 按精确报错把那几条改短

模型从头到尾**不会被要求"把它弄好看"**——好看是设计系统的事，
模型只需要在预算内把话说清楚。

## 目录职责

| 文件 | 职责 |
|---|---|
| `scripts/ink.py` | 渲染核心：手绘原语、13 种版式、页面装配、`CALIB` |
| `scripts/decor.py` | 装饰零件（齿轮/星形，纯 SVG path）+ 颜色轮换 |
| `scripts/build.py` | CLI：规格 → HTML（支持 yaml / json） |
| `scripts/plan.py` | CLI：页数规划（建议张数 + 每页骨架，把「推导」变成「答案」） |
| `scripts/capacity.py` | CLI：几何容量（每槽 ok / dense / overflow，规格门硬墙的依据） |
| `scripts/validate.py` | CLI：规格门（结构 + 几何硬违规，字数只提示） |
| `scripts/measure.py` | 真实浏览器文本测量（像素门）+ 方框清单比对 |
| `scripts/render.py` | CLI：HTML → PNG（后端选择 + 跨平台浏览器探测） |
| `scripts/cdp.py` | 纯标准库 CDP 客户端（默认渲染后端） |
| `scripts/pipeline.py` | 编排：build → measure → 修正循环 → render |
| `scripts/vision_probe.py` | 读图能力判定（多模态三态，看到底能不能看图） |
| `scripts/doctor.py` | 环境自检（含渲染后端预检） |
| `templates/contracts.yaml` | 每种版式的字数预算（**契约本体**） |
| `assets/style.md` | 视觉常量（配色、线宽、字号）的说明 |


## 文字排版：为什么是 DOM，而不是 SVG `<text>`

SVG `<text>` **没有文字排版能力**：不折行、没有 `text-overflow`、没有"按内容缩字号"，
一行 `<text>` 就是一串按坐标摆好的字形。于是"折行/居中/省略/缩放"全得自己算 ——
`wrap_text` / `fit` / 每槽的字数预算 / `CALIB` 校准回环 / `textLength` 注入，
这一整套机器都是为绕开这个限制而存在的，也是"每改一个视觉细节都要穿过几百行适配代码"的来源。

改法（用户定的方向，已落地）：**手绘墨迹继续用 SVG，文字交给 DOM**。

| | SVG 文字（旧） | DOM 文字（现在） |
|---|---|---|
| 折行 | 自己算（`wrap_text`） | `overflow-wrap: break-word` |
| 行数上限 | 自己算 + 截断成「…」 | `-webkit-line-clamp` |
| 垂直居中 | 自己算基线 | flex `align-items: center` |
| 字号自适应 | 自己估宽度 + 浏览器实测回写 | 一条 JS 循环（`scrollHeight > 槽高` → 缩 1px） |
| 高亮 `[[词]]` | 蜡笔色带（手工定位） | `.hl` 的 `::before` 蜡笔底色（同一套视觉） |
| 缺陷类别 | 孤字 / 劈词 / 压框线 / 容量随数量变化… 全靠自己算 | 折行由浏览器保证，只剩"真放不下"要人改文案 |

实现要点：
- 版式**只画墨迹**（`pen_box` / `arrow` / `dash_box`…），文字用 `_reg_slot(x, y, w, h, text, size, clamp)` 登记
- `render_card` 把 stage 包进 `.stagewrap`，覆盖一层绝对定位的 `.slots`；坐标系必须同源（`.stage` 的 margin 归零）
- 页面尾部注入 autofit 脚本：**与槽盒子比**（`el.scrollHeight > 槽.clientHeight`），不是与文字自己比
- 门禁侧：`measure.py` 收集 `rep.slots`（渲染矩形 / 计量字号 / 是否溢出 / 行盒），
  报 `dom-overflow`（真放不下）与 `dom-orphan`（末行 ≤2 字或 <20% 宽）；
  并把 DOM 槽纳入几何求交（`crosses-box` / `crosses-line` / `overlap`），与 SVG 文字对等

**迁移状态**（`text: "dom"` 时代已经过去，现在没有开关）：

| 版式 | 状态 |
|---|---|
| flow / chain / compare | ✅ 已迁（SVG 文字分支已删除） |
| bullets | ✅ 本来就是 HTML 行（浏览器排版） |
| hub / arch / cycle / spectrum / timeline / matrix / pyramid / cover（含四宫格 mini） | 迁移中 |
| raw | 透传原始 SVG，不涉及 |
