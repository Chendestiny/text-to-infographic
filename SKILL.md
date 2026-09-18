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

**四条命令就是全部工具面**（先看这张表，细节按需查）：

| 什么时候用 | 命令 | 它给你什么 |
|---|---|---|
| 决定拆几页 | `python scripts/plan.py <文章.md>` | 页数建议 + 区间 + **每页骨架**（别自己推） |
| 写完规格后过门（一次搞定） | `python scripts/check.py <spec.json> --article <文章.md>` | 预检 + 页数对账 + 规格门 + 像素门，一份结论 |
| 写文案**之前**看预算 | `python scripts/capacity.py <spec.json> --budget` | 每槽能放几个汉字（按真实几何算） |
| 写完规格 | `python scripts/validate.py <spec.json>` | 几何硬违规 / 密集档提示 / 建议值提示 |
| 想知道某槽能放几个字 | `python scripts/capacity.py <spec.json>` | 每槽 ok / dense / overflow 的**真实几何** |
| 出图 | `python scripts/pipeline.py <spec.json> -o <out>` | PNG + **四道门** + 降级报告 |
| 交付前预检（不用看图） | `python scripts/preflight.py <spec.json>` | 孤字 / 断词 / 数量词 / 贴边 |
| 想看观感时 | `python scripts/review_sheet.py <出图目录>` | 720px 单张缩略图（看图很贵，只抽查 1~2 张） |

---

## 一、五步流程

**第 1 步 · 环境**：`python scripts/doctor.py`
（Windows 上 `python` 不在 PATH 就用 `py -3`）。doctor 提示"只有 CDP 后端可用"时先设
`$env:T2I_BACKEND='cdp'`，否则截图会全是 0 字节。

**第 2 步 · 切页：跑脚本，别自己推**
```bash
python scripts/plan.py <文章.md>
```
它输出：汉字数 / 节数 / 每节字数 → **建议张数 + 允许区间 + 每页骨架**。
区间 **4~9 张**（6~9 是小红书平台偏好区，平台上限 18，超过 12 该拆系列）。
张数 ≈ 1（封面）+ 章节数；平均每节 <400 汉字两节并一页；全篇 <1.5k 汉字压到 4~5 张 ——
这些 plan.py 都替你算完并写出了推导。
**页数由"切法"决定，不随行数增长**：228 行是 7 张，1000 行也是 8~9 张，永远不是 100 张。
写完规格**拿脚本对一次账**（张数是硬数字，不是你发挥的地方）：

```bash
python scripts/plan.py <文章.md> --check <spec.json>
```

一致就过。不一致时它会列出建议骨架，并要求你把偏离理由写进 `spec.meta.plan_note` ——
**理由要具体到"骨架里哪一页承载不了原文的哪个重点"**，不是"我觉得 9 张好看"。

**第 3 步 · 写规格**：从 [examples/](examples/) 抄一个形状再改文案。
**先把骨架写成规格（版式和条数定了、文案留空），跑一次预算表**：

```bash
python scripts/capacity.py <骨架.json> --budget     # 每槽能放几个汉字，按真实几何算
```

这一步不是仪式 —— 实测（文章2 第 1 轮）agent 是**写完文案才发现**"cover 的 chips 只放得下
2 个汉字、flow 5 节点的标签只剩 ~117px、cycle 的 desc 只有 250px 宽"，于是返工 4 轮、28 次命令。
先看预算，这些返工在写之前就该消失。
- 版式字段表在 [docs/layouts.md](docs/layouts.md)，开头还有一张**字段支持总表**
  （`note` 在 bullets / compare / cycle / raw 上写了也不渲染，规格门会拦）
- **字数上限只是建议值 M**：真实能不能放下由几何说话。拿不准就跑 `capacity.py`
- 放不下时**先换版式或换写法**（一页 `bullets` 4~6 条、`chain` 5~6 步、`compare` 4+4 条），别硬塞
- 语法见本文「三、规格语法」

**第 4 步 · 过规格门**：`python scripts/validate.py <spec.json>`
- 「几何上放不下」= **硬违规**：会丢字（多行被截成「…」）或缩到 <28px 不可读 → 必须改短或换版式
- 「密集档」「超过建议字数」= 提示，不阻断（密集档 = 小一号字，视觉略不一致）
- 结构问题（未知字段 / note 不支持 / 条数越界 / 页数超平台）一律硬违规
**0 硬违规才继续。**

**第 5 步 · 出图，并看三个输出块**
```bash
python scripts/pipeline.py <spec.json> -o <out>
```
1. `measure: N 处溢出` / `verify:` —— 像素门 + **几何布局门**（同一趟浏览器测量，零额外成本）
2. `⚠ 降级报告` —— 引擎为了放下字做的妥协（缩字 / 密集档 / 截断 / 封面压扁），**逐卡点名**
3. `⚠ needs_llm` —— 脚本压不下的那几条，按报错改短再跑（兜底入口，不是失败）

几何布局门查这四类，**全部用 rect 求交/实测，不依赖任何视觉模型**：

| 问题 | 判定 | 说明 |
|---|---|---|
| `box-overflow` / `out-of-canvas` | 文字 rect vs 方框 / 画布 | 溢出与越界（位置用视觉 rect，认父级 transform） |
| `crosses-box` | 文字纵向穿出方框 | **备注压在方框下边框上**——肉眼最容易漏的一类 |
| `crosses-line` | 文字压到箭头/连线 | 连线穿过文字 |
| `overlap` | 两段文字互相压住 | 由 `hl_line` 拆分改写、或两块文案挤到一起 |

报错会带 `data-tag` 指名的槽位（`card-02 chain-note`），不用猜坐标。

**第 6 步 · 预检 →（可选）看图 → 交付**
两道门只保证"没溢出、没吞字"。交付前先跑**文字级预检**（0 秒、0 token、不需要看图）：

```bash
python scripts/preflight.py <spec.json>      # 孤字 / 断词 / 数量词 / 贴边
```

它管三类：**孤字**（末行只剩 1~2 字）、**断词**（拉丁词被折开）、**数量词**（标题写"两件事"却列了 4 条）。
压字·出框由像素门实测；**配色·疏密这一类才真的需要看图**。

**视觉只用于最后一道（可选）的审美抽查**：正确性已由几何门量完，视觉只判
「配色是否好看、疏密是否舒服」这类主观项 —— **最多 1 次、只抽查 1~2 张**，甚至可以不做。

看图很贵，**别当默认动作** —— 实测（本机 vision 走 qwen3.8-max，同一张封面图换了 7 个尺寸）：

| 尺寸 | 1440px | 1080px | 900px | 720px | 540px | 420px | 300px |
|---|---|---|---|---|---|---|---|
| 延迟 | 46.9s | 49.2s | 55.8s | **31.7s** | 60.2s | 73.1s | 66.4s |

**延迟与图片尺寸无关**（像素占 1.9% 的 300px 反而比占 44% 的 1440px 慢）——它是服务商波动。
真正决定成本的是**调用次数**和**输出长度**：一次问 4 张的拼版调用直接 >600s 未返回（输出和推理变长，
不是像素变多）。所以：

- **尺寸 720px 就够**：原图 2160×2880 对模型毫无收益（它自己会缩），白白多传 3 倍数据
- **一次只问一个问题、只要一行答案**（"每张一行 / 不要描述图片"）—— 输出越长越慢
- 文字可读性有余量：那张大标题 300px 还读得对，但正文小字（24~28px）在 300px 下只剩 3px、读不了，
  所以**别低于 540px**，**720px 是默认**

- **默认不看图**（推荐）：preflight + 几何门过了就交付，报告里写"审美未校验（可人工过目）"。
  实测这一条能省 1~2 分钟 —— 看图一次 40~115 秒，而且它总想输出整段"图像描述"。
- 要看就**最多 1 张**（封面），把下面这段原样发给看图模型（实测：不这么写它会输出整段"图像描述"，一次 40~80 秒）：

  **调用形状照抄**（两个参数，提示词一定要短，否则它会写小作文）：
  ```
  vision_analyze("review/thumb/card-01.jpg",
                 "只看三点，每点一行，不要描述图片：1) 有没有文字压在框线或箭头上？2) 有没有两段文字叠在一起？3) 配色是否协调？")
  ```
- 想看观感时：`python scripts/review_sheet.py <出图目录>` 生成 720px 单张缩略图，
  **只抽查 1~2 张**（封面 + 一张内容页），一句话问清楚（别让它写描述）
- **不要拼版**（一次问多张 → 输出变长 → 单次 >600s）、**不要逐张全看**、
  **改完文案不要重新看图**（文案改动由两道门验）
- 整轮视觉调用**预算 ≤2 次**；harness 没有 vision provider 就直接跳过，别去折腾配置

交付时附这段（**门禁输出逐字贴，别复述**）：

```
页数：7 页（plan.py 给 7，区间 4~9）
版式：01 cover / 02 bullets / 03 chain / 04 compare / 05 pyramid / 06 bullets / 07 chain
规格门：契约校验通过（7 页，在推荐区间 4~9 内，0 硬 / 0 软）
像素门：measure: 0 处溢出 / verify: 干净，进入渲染
降级报告：3 处（card-02 密集档 40px；card-05 缩字 42→30px 已改短重渲）
自检：7 张逐张看过，无新瑕疵
耗时：渲染 4.9s；写规格 + 复核约 X 分钟
```

---

## 二、编排分工（多篇 / 多页怎么并行）

| 环节 | 谁做 | 能并行吗 |
|---|---|---|
| 切页 + 页骨架 | `plan.py`（脚本） | 答案已经算好，不用模型推 |
| 写规格 | 你，或一个文案 subagent（输入 = 文章 + 骨架 + 字段表） | **能**：一篇 = 一个单元 |
| 渲染 + 两道门 | `validate.py` / `pipeline.py`（纯脚本，0 token） | 能但没必要（0.5s/页） |
| 逐张复核 | 看图 subagent（只报上面四类） | **能**：一次复核分 2~3 片 |

同一篇内部（写规格 → 过门 → 渲染 → 复核 → 返工）**必须串行**，有依赖。
**并发上限 2~3**：每个 subagent 一份独立上下文，每个渲染还要拉一个 Chrome。

---

## 三、规格语法

```json
{ "meta": { "footer": "", "frame": ["pen", "card", "none"], "decor": true,
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

- `meta.frame` 每页轮换：`pen` 手绘框 / `card` 圆角卡 / `none` 无框；`meta.decor` 控制装饰
- 标题里写 `\n` 可显式断行；单卡可覆盖 `frame`；chain / flow 支持 `dashed` + `dashed_label`
- **高亮**：`[[关键词]]` 自动轮换色（蓝→黄→粉→绿→灰→橙），`[[x|b]]` 指定色
  （`b` 蓝 / `y` 黄 / `p` 粉 / `g` 灰 / `gr` 绿 / `o` 橙）
- **上色**：方框默认全部上色、颜色自动轮换；想让某框留白表示"这步不重要"写 `"fill": "none"`；
  框已上色时框内文字不再画色带（引擎行为，不用处理）

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
| 页数 / 密度拿不准 | 本文第 2 步 + `plan.py` 的输出 |
| 报「几何上放不下」「密集档」 | [docs/contracts.md](docs/contracts.md) |
| 报未知字段 / note 不渲染 / 文案被截断 | [docs/troubleshooting.md](docs/troubleshooting.md) |
| 不知道某版式有哪些字段 | [docs/layouts.md](docs/layouts.md)（含字段支持总表） |
| 截图 0 字节 / 后端问题 / profile 冲突 | [docs/rendering.md](docs/rendering.md) |
| 想看"为什么这么设计" | [docs/architecture.md](docs/architecture.md) |
| 想加一种版式 | [docs/extending.md](docs/extending.md) |
| 交付前过一遍 | 下面这份清单 |

---

## 六、交付检查清单

- [ ] `validate.py` **0 硬违规**（几何墙）
- [ ] `pipeline.py` 没有 `needs_llm` 清单，且**降级报告已看过**（缩字 / 密集档 / 截断）
- [ ] 页数落在 `plan.py` 给的区间内（4~9）
- [ ] **跑过 `preflight.py`**（孤字 / 断词 / 数量词）且已改完；像素门 0 溢出、无遗漏的降级报告
- [ ] 交付时给了门禁逐字输出 + 页数理由 + 降级报告 + 自检结论
- [ ] 产物：`card-01..N.png`，默认 2160×2880（3:4 的 2 倍图）。
      要调风格改 `assets/style.md` 里的常量，**不要**改单页 HTML —— 一页一改风格就飘了