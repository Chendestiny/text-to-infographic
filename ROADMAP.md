# ROADMAP：项目现状与待办

> 给下一个接手的人（或 agent）：**先读这份，再读 [docs/testing.md](docs/testing.md)**（实测流程）与
> [docs/architecture.md](docs/architecture.md)（为什么这么设计）。README 是给用户看的介绍。

## 一、这个项目现在是什么样

**text-to-infographic**：长文 → 一套小红书/IG 竖版图文卡。**确定性渲染**（不是 AI 生图）：
文字永远清晰、同一份规格永远出同一套图、每页可手改。

**核心架构（2026-09 大改后）**：

| 层 | 现状 |
|---|---|
| 手绘墨迹（方框/箭头/色带/装饰） | SVG 路径，由 `scripts/ink.py` 生成 |
| **文字** | **DOM**：版式只登记"槽"（矩形 + 起手字号 + 行数上限），**折行 / 行数上限 / 垂直居中 / 字号自适应全部交给浏览器** |
| 字号自适应 | 页面尾部注入 ~15 行 JS：与**槽盒子**比 `scrollHeight/clientHeight`，缩到放下为止 |
| 高亮 `[[词]]` | `_inline()` → `<span class="hl y">`，用现成的 `.hl::before` 蜡笔底色（与 SVG 时代视觉一致） |

**13 个版式全部已 DOM 化**（`arch / bullets / chain / compare / cover / cycle / flow / hub / matrix / pyramid / raw / spectrum / timeline`），
验收证据：逐版式检查"stage 里 `<text>` 元素 = 0"（`bullets` 本就是 HTML 行、`raw` 是透传）。

## 二、工具面（agent 只需要记这些）

```bash
python scripts/run.py --plan <文章.md>                          # 页数 + 区间 + 页骨架 + 可粘贴 meta.plan
python scripts/run.py <spec.json> --budget --no-render          # 每槽尺寸/起手字号 + 预检 + 规格门
python scripts/run.py <spec.json> --article <文章.md> --out 目录 # 交付：四道门 + 出图 + 缩略图 + 结论 + 交付报告
```

`run.py` 自己调这些（**不要分头跑**，实测那样会让一轮多出 20+ 次命令调用）：
`plan.py / preflight.py / validate.py / capacity.py / pipeline.py / review_sheet.py`

`pipeline.py` 再把 `ink.py`（库）/ `measure.py` / `render.py` 当模块导入。
**只有 `build.py` / `doctor.py` / `vision_probe.py` 是独立 CLI**，不走交付流程：
`doctor.py` 是环境自检（SKILL.md 第 1 步要单独跑）、`build.py` 是"规格→HTML"的单步调试入口、
`vision_probe.py` 判读图能力。

**四道门**：
1. 文字级预检（数量词 vs 实际条数；孤字/断词已移到浏览器侧）
2. 规格门（结构：未知字段、note 是否可渲染、条数、页数上限）
3. 像素门 + 几何布局门（真实浏览器 `getBBox`/`getBoundingClientRect`；`dom-overflow` / `dom-orphan` / `crosses-box` / `crosses-line` / `overlap`）
4. 内容门（规格里登记过的文字必须真的出现在图上）

## 三、已完成（含证据）

| 阶段 | 提交 | 证据 |
|---|---|---|
| flow 迁 DOM | `a03bf8b` | `layout_flow` 内 SVG 文字调用 = 0 |
| compare + chain 迁 DOM + 修复孤字检查 | `34c21f2` / `ea6cd72` | 两版式内 SVG 文字调用 = 0；10 份示例 exit=0 |
| 提速：一条命令 + 预算并入 | `4cf613a` | `run.py` 成为唯一入口 |
| 全版式 DOM（改三个辅助函数而非 39 处调用点） | `5977bec` | **13/13 版式 `stage` 内 `<text>` = 0** |
| 删机器（第一批 44 行 + `fit()`） | `0eccaa2`、`b924c3e` | `ink.py` 1763 → 1717 行 |
| 修坏提交 + `run.py` 崩溃检测 | `82e8dfc` | 故意破坏 ink.py 实测：`✗ 像素门｜pipeline 异常退出（exit=1）` |
| 交付报告自动填写 | `4b02521` | 跑一份示例可见"页数/版式/门禁/降级/自检"已填 |
| 入口收敛（`--plan`） | `58f8feb` | 无参数打印用法；交付模式未破坏 |
| 文档全面更新（删过期机制） | `d3ffd3c`、`da9f816`、`598f09a`、`f2f9570` | 过期关键词复扫 0 处；相对链接全部有效 |
| 删 `txt_block` / `hl_line` 的不可达 SVG 尾巴（含拆掉 `if True:` 包裹层） | `f0d7a2f` | `ink.py` 1717 → 1658 行；顶层定义 94 → 94 **一条不少**；5 份示例 pipeline exit=0 |
| 文档补课：四道门口径、`run.py --plan` 入口、迁移状态 13/13 | `8495296` | `architecture.md` / `SKILL.md` / `README.md` / `README.en.md` / `docs/README.md` 与 ROADMAP 对齐；过期口径复扫 0 处；107 个相对链接全部有效 |

**速度**：三轮均值 **198.7s**（SVG 基线 377s，**-47%**），最快 139.6s；**180s 目标在 2/3 轮达成**。

## 四、已知技术债（别装看不见）

1. **残留死代码**（`txt_block` / `hl_line` 的不可达尾巴已于 `f0d7a2f` 删除，剩下这些）：
   `_reg_cap()` 现在**一个调用点都没有**（`f0d7a2f` 删掉了最后两处不可达调用），
   `_CAPS` 因此恒为空表，但它的管路还在：`ink.py` 的 `_CAPS.clear()` 与
   `<!--T2I_CAPS:...-->` 清单、以及 `capacity.py` 里读 `ink._CAPS` 的 judge 路径。
   功能零影响（空表进去、空表出来）。**清理要点：用"显式文本区间"切，别用 `def` 边界**
   （上次用边界切，连带删掉了 `class Palette` 与 `HL_RE` 常量，推了坏版本 `e7d485f`，后由 `82e8dfc` 回滚）。
   每次切完必须：① 对比切前切后的**全部顶层定义**（def/class/常量）② 跑 5 份示例的 **pipeline exit code**。
2. **`templates/contracts.yaml` 里 101 条 `max:`** 现在只是写作建议（`validate.py` 已把它们降为提示），可瘦身。
3. **`preflight.py`** 里靠 Python 估算折行的检查已删（被浏览器侧 `dom-orphan` 取代），仅保留"数量词"检查。
4. **方差**：三轮 139.6~287s，差 2.06 倍。最大值那轮用了 **45 次 API 调用**（其余 29/26）——
   值得用 `hermes_timeline.py` 拆那一轮的会话，看它多绕在哪一段。

## 五、TODO（按性价比排序）

| # | 事项 | 验收标准 |
|---|---|---|
| 1 | **削方差**：分析 287s 那轮的会话轨迹，找出多出的 ~16 次调用花在哪，并针对性改文档/脚本 | 三轮都 ≤200s，最好两轮 ≤180s |
| 2 | **安全清死代码**（`txt_block` / `hl_line` 的尾巴已由 `f0d7a2f` 清掉；**剩下** `_reg_cap` / `_CAPS` 管路与 `capacity.py` 的 judge 路径） | `ink.py` 再减 ~40 行；5 份示例 pipeline exit=0；顶层定义一条不少 |
| 3 | **契约瘦身**：把 `max:` 改成显式的"建议值"字段（或移到 docs），让 YAML 只留结构与条数约束 | 规格门行为不变；YAML 行数显著下降 |
| 4 | **给门加自测**：把 5 份示例 + 12 处已知反例（孤字、压框、劈词、超长）做成 `tests/`，一条命令跑完 | `python tests/run.py` 全绿 |
| 5 | ~~**Gitee 镜像同步**~~ **已基本达成**：实测镜像只落后 1 个提交（缺 `ROADMAP.md` 与 `docs/testing.md`，即 `cf037a3` 新增的两个文件）；`install.ps1` 与 `scripts/ink.py` 已与 GitHub 逐字节一致 | 推一次 `cf037a3` 后 `ROADMAP.md` 不再是 404 |
| 6 | 复核 `docs/troubleshooting.md` 里"标题自动缩字号"那段（`h1_html` 仍会缩 ✓ 属正常） | 读一遍确认无过期描述 |

## 六、文档索引

| 文件 | 讲什么 |
|---|---|
| [README.md](README.md) | 给用户：装、用、效果、页数区间 |
| [SKILL.md](SKILL.md) | **给 agent 的操作手册**（五步流程 + 命令 + 检查清单 + 症状路由表） |
| [docs/testing.md](docs/testing.md) | **怎么实测耗时与质量**（hermes 多轮流程、脚本、坑） |
| [docs/architecture.md](docs/architecture.md) | 为什么是"DOM 文字 + SVG 墨迹"、四道门的分工、迁移状态 |
| [docs/contracts.md](docs/contracts.md) | 契约语义（结构=硬、字数=建议、DOM 槽实测=硬） |
| [docs/layouts.md](docs/layouts.md) | 13 个版式的字段与写作建议 |
| [docs/extending.md](docs/extending.md) | 加新版式：只画墨迹 + `_reg_slot` 接口 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 报错处置（`dom-overflow` / `dom-orphan` / 页面被裁…） |
| [docs/rendering.md](docs/rendering.md) | 渲染后端、@1x/@2x、看图成本实测 |