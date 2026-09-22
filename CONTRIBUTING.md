# Contributing

感谢你愿意改这个东西。先说三条最容易踩的规矩，再说流程。

## 三条硬规矩

### 1. 别分头跑脚本，只用 `run.py`

`run.py` 已经把 `plan.py` / `preflight.py` / `validate.py` / `capacity.py` /
`pipeline.py` / `review_sheet.py` 全部并在一条命令里，结论也是它出。

分头跑不只是多花时间（实测一轮多出 20+ 次命令调用），**更危险的是会读错结果** ——
本项目抓到的一系列 bug 都属于"子脚本崩了 / 输出被截断，而调用方当成没事"。
`run.py` 现在会对每个阶段做超时与"有没有跑完"的判断，绕过它就没了这层保护。

### 2. 验收看退出码，不看关键词

```bash
python scripts/run.py <spec.json> --out <目录> ; echo "exit=$?"
```

`exit=0` 才是可交付。**不要**在输出里扫"✓""通过"之类的字样下结论。
历史上出现过 `ink.py` 被裁坏、`run.py` 仍报"硬问题 0 处"的假绿。

### 3. 中英 README 必须对齐

`README.md` 与 `README.en.md` 的章节编号、条目数量要一一对应。
改了一个就改另一个。两份已经漂移过一次，同步是成本，不同步是坑。

## 提交前请跑一遍

```bash
python -c "import yaml"        # 硬依赖，缺了规格门跑不起来
python scripts/doctor.py
python tests/run.py            # 31 条，约 70 秒
```

`tests/run.py` 里每条测试都对应一次真实踩坑，docstring 写了它守的是什么。
**新增断言时，请在 docstring 里写清楚"它防的是哪次事故"** —— 否则下一个人
（很可能就是几个月后的你）会因为看不出价值而把它删掉。

### 为什么对测试这么较真

一轮返工 ≈ 一次 LLM 往返（50~90 秒），而脚本只要 6 秒。
所以这个项目最贵的失效模式不是"跑得慢"，而是**悄悄多一轮返工**。
在测试里拦住它，比在真机上便宜得多。

## 改渲染（`scripts/ink.py`）时

- 改完跑 `python tests/run.py` 的 `TestLayoutSmoke`：15 种版式每种都要出图。
- 文字相关的改动，重点看**降级报告**（`run.py` 结论里的那段）——
  被自动缩字号/挤档的地方会列在那里。
- 别改 `overflow-wrap: break-word` 和 `word-break: normal`：
  DOM 侧"不劈词"是靠这条 CSS 保证的，改了四道门一声不响，图却会开始劈词。
- **主题令牌不能用 Python 默认参数接**：`def pen_path(segs, color=INK)` 是 def 期绑定，
  换皮肤时永远拿到首次导入的值。要 `color=None` 再在函数体里回落到 `INK`。

## 想加皮肤？

往 `scripts/theme.py` 的 `THEMES` 加一条字典就行，**`ink.py` 一个字都不用改**
（除非你要加一种新的高亮形态或新的 CSS 钩子）。

**先想清楚属于哪个族**（这是最容易搞错的一步）：

- `family: "paper"` —— 节点是**上色方框**，强调靠整块底色。跟着 `crayon` 走就行。
- `family: "diagram"` —— 节点是**细描边 + 左侧强调轨**，配 `node_surface` / `node_line` /
  `node_w` / `rail_w` 这几个令牌。别把纸张族的高饱和调色板直接搬过来当填充色
  （踩过：暗夜终端里一块块荧光填充块，跟"工程图"完全打架）。

六条纪律写在 `theme.py` 的模块 docstring 里。加完：

```bash
python make_theme_gallery.py --family paper    # 出到桌面 t2i-themes/，看图挑
python tests/run.py                            # TestTheme 那几条会盯住"只换了一半"
```

## 改图鉴？

三个可视化脚本共用 `scripts/sheet.py`（拼版工具）。**README 只用拼版，不用一行一张的图片表格** ——
图片表格在手机上会把页面撑成瀑布，而且每个 `<img>` 都是一次请求。

```bash
python make_layout_gallery.py                                  # → docs/images/layouts/版式图鉴.png
python make_theme_gallery.py --strips-out docs/images/showcase  # → README「出图效果」那 7 条横条
python make_theme_gallery.py --family paper -o <桌面目录>        # 逐套皮肤翻样张（挑皮肤时用）
python make_style_probe.py --layout chain --styles A,G          # 方框样式比选 → 桌面 t2i-box-styles/
```

> README 只用拼版和横条，**一行一张的图片表格不要**（手机上撑成瀑布，每个 `<img>` 都是一次请求）。
> 跨皮肤对比表（`--sheet-out`）有 872 KB，按需生成、不进仓库 —— 皮肤长什么样看横条已经够了。

> 图鉴样张讲的必须是**同一件事**：封面写着 A 题、后七张讲 B 题，放在拼版里一眼就是拼凑的
> （这条是被用户点出来的，别再犯）。

**调节点外观时用 `make_style_probe.py`**：它固定「一套皮肤 + 一个版式」，只换
`node_style` / `node_radius` / `node_line` 这些令牌，把多个方案拼成一张对照表。
比直接改 `theme.py` 再跑整套图鉴快得多，也不会因为版式差异混淆判断。

## 提交信息

随意，但请写清楚**为什么**。本项目很多注释都以"踩坑："开头记录当时的上下文，
因为半年后没人记得为什么那行不能删。

## 想加版式？

读 `docs/layouts.md`，再照 `scripts/ink.py` 里 `layout_*` 的写法加一个。
加完请在 `tests/run.py` 的 `LAYOUT_CARDS` 里补一条，并重新生成样张：

```bash
python make_layout_gallery.py
```
