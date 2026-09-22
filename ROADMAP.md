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
| 高亮 `[[词]]` | `_inline()` → `<span class="hl y">`，用现成的 `.hl::before` 底色（形态由皮肤决定） |
| **皮肤** | `scripts/theme.py` 一组设计令牌，`meta.theme` 切换；分**纸张族**（复用版式，已定稿）与**工程族**（节点重画过，版式待定） |

**15 个版式全部已 DOM 化**（`arch / bullets / chain / compare / cover / cover_quote /
cover_title / cycle / flow / hub / matrix / pyramid / raw / spectrum / timeline`），
验收证据：逐版式检查"stage 里 `<text>` 元素 = 0"（`bullets` 本就是 HTML 行、`raw` 是透传）。
版式烟雾测试已覆盖全部 15 种。

## 二、工具面（agent 只需要记这些）

```bash
python scripts/run.py --plan <文章.md>                          # 页数 + 区间 + 页骨架 + 可粘贴 meta.plan
python scripts/run.py <spec.json> --budget --no-render          # 每槽尺寸/起手字号 + 预检 + 规格门
python scripts/run.py <spec.json> --article <文章.md> --out 目录 # 交付：四道门 + 出图 + 缩略图 + 结论 + 交付报告
python scripts/run.py <spec.json> --only N --out 目录            # 单页返工：1~2 秒，其余页不动
python tests/run.py                                             # 自测：27 条，约 60 秒
python make_layout_gallery.py                                   # 版式图鉴：14 张样张拼成一张
python make_theme_gallery.py --family paper                     # 皮肤图鉴：纸张族 3 套 × 8 张样张（出到桌面）
```

`run.py` 自己调这些（**不要分头跑**，实测那样会让一轮多出 20+ 次命令调用）：
`plan.py / preflight.py / validate.py / capacity.py / pipeline.py / review_sheet.py`

> ⚠ **跑之前确认解释器装了 pyyaml**：规格门要拿它解析契约本体 `templates/contracts.yaml`，
> 与规格是不是 `.json` 无关。本机 `python` 一度指向没装 pyyaml 的解释器，
> 结果是**规格门静默跳过、run.py 还报 exit=0**（已由 `976eca7` 修成硬问题）。
> 一句话自检：`python -c "import yaml"`。

`pipeline.py` 再把 `ink.py`（库）/ `measure.py` / `render.py` 当模块导入。

### 两个远程，推送要一起

| remote | 地址 | 说明 |
|---|---|---|
| `origin` | `github.com/Chendestiny/text-to-infographic` | 主仓库 |
| `gitee` | `gitee.com/destinychen/text-to-infographic` | 国内镜像（`install.ps1` 探不通 GitHub 时会走它） |

README 承诺"两个仓库内容同步"，所以推完记得 `git push gitee main` —— 漏推会让国内用户装到旧版本。
本机 `gitee` 凭据已存在凭据管理器里，不用额外登录。

> **身份纪律**：本仓库的提交身份是**仓库级** `.git/config`（`Chendestiny <42106833+Chendestiny@users.noreply.github.com>`），
> 全局配的是公司身份。新建仓库时第一件事就是补仓库级身份，否则会像 2026-09 那样
> 混进 44 个 `chensongqi@neware.com.cn` 的提交（已用 `filter-branch` 改写 + 两个远程 force push 修掉）。
> 推之前抽查：`git log --format='%ae|%ce' | sort -u`。
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
| **主题（皮肤）系统 + 两种标题封面 + 工程族节点重画** | 本轮 | 7 套皮肤分两族；`make_theme_gallery.py` / `make_layout_gallery.py` / `make_style_probe.py` 三张图鉴；`--theme` 开关；32 条测试全绿；10 份示例 exit=0 |
| **文章4 多皮肤实测**（`4 提示词工程.md` 3424 汉字 → 8 张） | 本轮 | 随机 3 套皮肤 `retro` / `crayon` / `blueprint`：**exit=0、0 处溢出、逐页四门全过、5.8~6.0s 墙钟**（pipeline 3.8~3.9s），8 张 × 2.3~2.8 MB |
| 本地实测（文章4 / 文章5，不走 hermes）揪出 5 个真 bug + 2 处样式问题 | `0e76d4d`、`3af40ed`、`277747d`、`976eca7`、`3c37db6`、`d664f63`、`5ac1880` | 见下方《文章4 / 文章5 本地实测》；10 份示例（5 json + 5 yaml）仍 exit=0 |

**速度**：三轮均值 **198.7s**（SVG 基线 377s，**-47%**），最快 139.6s；**180s 目标在 2/3 轮达成**。

### 文章4 / 文章5 本地实测揪出的 bug（都已修）

不走 hermes、直接在本会话跑 `4 提示词工程.md`（3424 汉字 → 8 张）与
`5 向量化向量库与实践.md`（2934 汉字 → 7 张）时踩到的。
**都不是"agent 不够小心"，是脚本自己矛盾、给了假信号，或者门根本没跑。**

| # | 现象 | 根因 | 修法 |
|---|---|---|---|
| 1 | 按文档填了 `meta.plan.note`，门禁却说「没写偏离理由」 | `plan.py --check` 只读 `meta.plan_note`，而**它自己打印的模板**和**紧挨的报错文案**都写 `meta.plan.note`（`validate.py` 两个都认）→ 照文档做必踩 | 优先读 `meta.plan.note`，回退旧键（`0e76d4d`） |
| 2 | **两条孤字提示让整轮 `exit=1`**，白跑 2 轮返工 | SKILL.md 明写 `dom-orphan` 是「提示，能改就改」、只有 `dom-overflow` 和页数超限才拉回 LLM；但 `pipeline.py` 把它和 `dom-overflow` 同桶 → 进 `needs_llm` → 被 `run.py` 判成硬问题 | 新增 `SOFT_KINDS`，孤字单独一桶；`N 处溢出` 只数硬问题（`3af40ed`） |
| 3 | `--budget` 对**已知会溢出**的规格报「所有槽都放得下 ✓」 | 文字槽全迁 DOM 后 `_reg_cap` 没了调用点 → `ink._CAPS` 恒空 → `capacity.py` 的判定循环一次都没跑过 | 判空时明说"没判定"；DOM 槽补「约 N 字（缩到下限 M 字）」（`277747d`） |
| 4 | **规格门（第③道门）从来没跑过，而 run.py 报 `exit=0`** | 本机 `python` 指向的解释器没装 pyyaml，而 `validate.py` **无条件** `import yaml`（在判断扩展名之前）→ 每次 `.json` 规格都 `SystemExit`。`run.py` 只看 `pipeline.py` 的退出码，前两道门的退出码直接丢掉，只靠关键词找结论行 → 崩溃时没有结论行，就落进「有提示，见下」 | run.py 把"门没有结论行"判为硬问题；`validate.py` 改成惰性导入 + **无条件打印结论行**（`976eca7`） |
| 5 | 安装脚本与 README 都说「`.json` 规格零第三方依赖」 | 契约本体 `templates/contracts.yaml` 就是 YAML，规格门**离不开 pyyaml**，与规格扩展名无关。这句错承诺正是 #4 被忽视的原因 —— 它读起来像"缺 pyyaml 是受支持的配置" | 五处（requirements / install.sh / install.ps1 / README 中英）改成硬依赖并写明理由（`3c37db6`） |

顺带修的三处报告缺陷：

- `needs_llm` 只带 `(页, 文案)`，把 issue 的 `note`（**实测像素值**）丢了 ——
  报错只说"这条不行"、不说"差多少"。现在带上：
  `← DOM 槽放不下：内容 157px 高 / 容器 73px（字号 31，已缩到下限）`
- `run.py` 只把「需要 LLM 重写」**标题行**记进结论，逐条明细全丢 → 结论等于没说，
  还得回头手跑一次 `pipeline.py`（这本身又是一整轮）
- 交付报告去 `review_sheet` 的输出里找规格门结论（`o` 被重新赋值了），
  所以那行永远是「（有提示，见上）」

### 稳定性 + 人在回路（`0b462d9` / `fff466a`）

用户的主线诉求：**3~4 分钟可以接受，但"10 次至少 4 次卡壳"不可接受**；
以及提速后质量偶有下降，需要能**单独返工某一张图**。

**卡壳的结构性根因**：`run.py` 的 `subprocess.run` **没有任何 timeout**。
全仓库其它外部调用都有界（`_wait_port` 25s、`_cmd` 120s、CLI 渲染后端），
唯独"调起了所有门"的那个编排器没有 —— 任何一道门挂住就是无限等待。

| 措施 | 说明 |
|---|---|
| 阶段超时 | 各门 60s、pipeline 600s（实测耗时 <1s / ~1s 每页，留 30~80 倍余量）。
  超时明确报 `✗ pipeline.py 超时（600s，已强制中止）` 并退出，不再挂死 |
| 自动重试 | 像素门崩溃/超时**自动重试 1 次**（浏览器冷启动、profile 被占是主要抖动源） |
| 渲染失败不再被吞 | `shoot()` 失败原来只进日志、退出码仍是 0 → "8 张里 1 张没出"
  被当干净交付。现在点名缺哪张、退出码非零；`shoot()` 抛异常只废一张、不拖死整套 |
| 产物独立核对 | run.py 自己数一遍 `card-NN.png` 是否存在且非空，
  **不信任上游的自我报告** |
| 超时可测 | `T2I_TIMEOUT_SCALE=0.002` 可整体缩放 —— 否则超时这条路径根本没法验证 |
| 不删好图 | `node_render` 原来**先清空所有 PNG 再渲染** → card-03 失败会把 01/02
  的好图一起删掉（"1 张失败"升级成"整套没了"）。改成成功后才清理残留旧图 |

**人在回路：`run.py <spec> --only N`** —— 只重建/重测/重出第 N 页，**1~2 秒**，
其余页 HTML 与 PNG 一字不动。SKILL.md 已文档化，agent 才知道该用它。

验证：文章5 连跑 5 次 **exit=0、6~8s**，无卡壳；强制让 card-03 渲染失败时，
其余 6 张完好、仅 03 缺失并被点名。

> **待办**：本节这些断言（超时会退出、渲染失败 exit≠0、单页返工不动其它页）
> 该进 `tests/`（TODO #4），否则下次改渲染链路还可能悄悄退化。

> **教训**：这几条都属于「文档承诺 A、代码做 B」或「门没跑却报绿」。
> 单靠读文档发现不了 —— 必须真跑，并且**怀疑每一个"✓"**。
> 最危险的不是没检查，是**以为已经检查过了**。

## 四、已知技术债（别装看不见）

1. **残留死代码**（`txt_block` / `hl_line` 的不可达尾巴已于 `f0d7a2f` 删除，剩下这些）：
   `_reg_cap()` 现在**一个调用点都没有**（`f0d7a2f` 删掉了最后两处不可达调用），
   `_CAPS` 因此恒为空表，但它的管路还在：`ink.py` 的 `_CAPS.clear()` 与
   `<!--T2I_CAPS:...-->` 清单、以及 `capacity.py` 里读 `ink._CAPS` 的 judge 路径。
   ⚠ **这不是无害的**：`277747d` 之前，`capacity.py` 因为判的是恒空表，
   会输出「所有槽都放得下 ✓」的**假绿**（实测对一份有 3 处真溢出的规格照样报绿）。
   现已改成"判空时明说没判定"+ 给 DOM 槽补几何参考线，但**空表管路本身还在**，
   属于该清的债。**清理要点：用"显式文本区间"切，别用 `def` 边界**
   （上次用边界切，连带删掉了 `class Palette` 与 `HL_RE` 常量，推了坏版本 `e7d485f`，后由 `82e8dfc` 回滚）。
   每次切完必须：① 对比切前切后的**全部顶层定义**（def/class/常量）② 跑 5 份示例的 **pipeline exit code**。
2. **`templates/contracts.yaml` 里 101 条 `max:`** 现在只是写作建议（`validate.py` 已把它们降为提示），可瘦身。3. **`preflight.py`** 里靠 Python 估算折行的检查已删（被浏览器侧 `dom-orphan` 取代），仅保留"数量词"检查。
4. **方差**：三轮 139.6~287s，差 2.06 倍。最大值那轮用了 **45 次 API 调用**（其余 29/26）——
   值得用 `hermes_timeline.py` 拆那一轮的会话，看它多绕在哪一段。
5. **契约本体是 YAML → 规格门硬依赖 pyyaml**（`3c37db6` 已把五处文档说准）。
   若想让「`.json` 规格零依赖」这个卖点真正成立，得让 `validate.py` 不再需要 pyyaml ——
   给 `contracts.yaml` 配一份 JSON，或只解析它真正用到的字段。目前 `.json` 规格
   **省不掉** pyyaml，README 已如实说明。

## 五、TODO（按性价比排序）

| # | 事项 | 验收标准 |
|---|---|---|
| 1 | **削方差**：分析 287s 那轮的会话轨迹，找出多出的 ~16 次调用花在哪，并针对性改文档/脚本 | 三轮都 ≤200s，最好两轮 ≤180s |
| 2 | **安全清死代码**（`txt_block` / `hl_line` 的尾巴已由 `f0d7a2f` 清掉；**剩下** `_reg_cap` / `_CAPS` 管路与 `capacity.py` 的 judge 路径） | `ink.py` 再减 ~40 行；5 份示例 pipeline exit=0；顶层定义一条不少 |
| 3 | **契约瘦身**：把 `max:` 改成显式的"建议值"字段（或移到 docs），让 YAML 只留结构与条数约束 | 规格门行为不变；YAML 行数显著下降 |
| 4 | ✅ **已做**（`4c26acb`）：`python tests/run.py` —— 14 条测试、约 75 秒。
分组：示例回归 / 严重度分级 / 报错要说清楚 / 页数与预算 / 可靠性兜底。
每条都对应一次真实踩坑，docstring 里写了它守的是什么。
**它是防"轮次悄悄变多"的** —— 一轮返工 ≈ 一次 LLM 往返（50~90s），
而脚本只要 6s，所以"退化成多跑几轮"是这个项目最贵的失效模式，
在测试里抓住它比在真机上便宜得多 |
| 4b | ✅ **已做**：① 版式烟雾测试（**15 种**版式每种都出图）② 不支持的字段会被点名
  ③ **CI**（`945d795`，`.github/workflows/ci.yml`，ubuntu + windows 跑 `tests/run.py`）
  —— 顺带修了 `render.py` CLI 兜底缺 `--no-sandbox`（容器里以 root 跑时两条路都起不来，
  "自动降级"等于没降级） |
| 4c | ✅ **已做**：压框 / 压线用**合成测量报告**直接喂 `measure.analyze()`
  （不启浏览器 → 确定性且只要 0.01s）；劈词改为守住那条 CSS
  （DOM 侧靠 `overflow-wrap: break-word` + `word-break: normal` 保证不切词内，
  **不是门检出来的**，所以改坏了门不会响，只能靠这条断言）
  ❗ 仍缺：压框/压线的**端到端真实渲染**反例（合成数据无法证明真实渲染也对） |
| 5 | ✅ **已做**：分发配套（`CHANGELOG.md` / `CONTRIBUTING.md` / `SECURITY.md` /
  `pyproject.toml` / `.claude-plugin/plugin.json`），两份 README 已补
  「开发与自测」段并链到新文件 | — |
| 5 | ~~**Gitee 镜像同步**~~ **已基本达成**：实测镜像只落后 1 个提交（缺 `ROADMAP.md` 与 `docs/testing.md`，即 `cf037a3` 新增的两个文件）；`install.ps1` 与 `scripts/ink.py` 已与 GitHub 逐字节一致 | 推一次 `cf037a3` 后 `ROADMAP.md` 不再是 404 |
| 6 | 复核 `docs/troubleshooting.md` 里"标题自动缩字号"那段（`h1_html` 仍会缩 ✓ 属正常） | 读一遍确认无过期描述 |
| 7 | 🟡 **进行中**：**主题（皮肤）系统** —— 分两个族（`theme.family`）：
  **纸张族**（`crayon` / `grid` / `retro`）复用现有版式；
  **工程族**（`terminal` / `blueprint` / `mono` / `nord`）节点按用户口径重画：
  透明底 + 主题色细描边 + 无笔锋；终端/蓝图用四角刻度，素白/北欧只用细线（北欧线宽 4.8）。
  已做：删 `morandi` / `brutal`、两张拼版图鉴（`scripts/sheet.py`）、两种新封面版式、
  **`--theme` 命令行开关**（`run.py` / `pipeline.py`）、`make_style_probe.py` 方框比选、32 条测试。
  **文章4 实测**（`4 提示词工程.md`，3424 汉字 → 8 张）：随机 3 套皮肤
  `retro` / `crayon` / `blueprint` 全部 **exit=0、0 处溢出、5.8~6.0s 墙钟**（pipeline 3.8~3.9s）。
  **剩下的**：① 工程族的版式本身（现在只是把纸张版式换了个节点画法）
  ② 皮肤级字体分发 ③ 端到端的真实渲染反例（压框/压线还是合成数据） |
  **第 1、2 类都能交付；正式图鉴只放了第 1 类** |

## 六、文档索引

| 文件 | 讲什么 |
|---|---|
| [README.md](README.md) | 给用户：装、用、效果、页数区间 |
| [SKILL.md](SKILL.md) | **给 agent 的操作手册**（五步流程 + 命令 + 检查清单 + 症状路由表） |
| [docs/testing.md](docs/testing.md) | **怎么实测耗时与质量**（hermes 多轮流程、脚本、坑） |
| [docs/architecture.md](docs/architecture.md) | 为什么是"DOM 文字 + SVG 墨迹"、四道门的分工、迁移状态 |
| [docs/contracts.md](docs/contracts.md) | 契约语义（结构=硬、字数=建议、DOM 槽实测=硬） |
| [docs/layouts.md](docs/layouts.md) | 15 个版式的字段与写作建议 |
| [assets/style.md](assets/style.md) | **主题（皮肤）令牌**、配色、笔锋、装饰零件库 |
| [docs/extending.md](docs/extending.md) | 加新版式：只画墨迹 + `_reg_slot` 接口 |
| [docs/troubleshooting.md](docs/troubleshooting.md) | 报错处置（`dom-overflow` / `dom-orphan` / 页面被裁…） |
| [docs/rendering.md](docs/rendering.md) | 渲染后端、@1x/@2x、看图成本实测 |