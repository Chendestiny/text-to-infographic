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
  │                   │     └ 版式类 → needs_llm 清单 → LLM 改文案 → 重跑
  │                   └─ render.py         HTML → PNG
  └─────────────────────────────────────────────────> out/card-01..N.png
```

`pipeline.py` 是 LangGraph 风格的状态机（State / Node / Conditional Edge），
但**不依赖 langgraph 包**——节点就是函数，状态就是一个 dict。需要时可以平移。

## 两道门为什么都要有

| 门 | 成本 | 抓什么 | 漏什么 |
|---|---|---|---|
| 规格门 `validate.py` | 毫秒，纯字符串 | 文案超契约（**90% 的问题**） | 字体度量导致的真实宽度偏差 |
| 像素门 `measure.py` | 秒级，要起浏览器 | 真实渲染出来的溢出（宽度/纵向） | 审美（配色、间距观感） |

**能机械校验的绝不交给模型判断。** 两道门都是纯脚本，不花 token；
只有像素门把某几条升级成 `needs_llm` 时，模型才回来改文案。

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

1. **事前**：读文章 → 决定拆几页 → 选版式 → 在契约字数内写文案
2. **事后**：像素门报 `needs_llm` 清单 → 按精确报错把那几条改短

模型从头到尾**不会被要求"把它弄好看"**——好看是设计系统的事，
模型只需要在预算内把话说清楚。

## 目录职责

| 文件 | 职责 |
|---|---|
| `scripts/ink.py` | 渲染核心：手绘原语、13 种版式、页面装配、`CALIB` |
| `scripts/decor.py` | 装饰零件（齿轮/星形，纯 SVG path）+ 颜色轮换 |
| `scripts/build.py` | CLI：规格 → HTML（支持 yaml / json） |
| `scripts/validate.py` | CLI：字数契约校验（规格门） |
| `scripts/measure.py` | 真实浏览器文本测量（像素门）+ 方框清单比对 |
| `scripts/render.py` | CLI：HTML → PNG（后端选择 + 跨平台浏览器探测） |
| `scripts/cdp.py` | 纯标准库 CDP 客户端（默认渲染后端） |
| `scripts/pipeline.py` | 编排：build → measure → 修正循环 → render |
| `scripts/vision_probe.py` | 读图能力判定（多模态三态，看到底能不能看图） |
| `scripts/doctor.py` | 环境自检（含渲染后端预检） |
| `templates/contracts.yaml` | 每种版式的字数预算（**契约本体**） |
| `assets/style.md` | 视觉常量（配色、线宽、字号）的说明 |
