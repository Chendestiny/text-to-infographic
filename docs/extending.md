# 扩展：加一种新版式

以加一个 `pyramid`（金字塔）版式为例。**五步，缺一步就会被后续维护卡住。**

> **文字排版已改为 DOM**：折行 / 行数上限 / 垂直居中 / 字号自适应都由浏览器负责，引擎只给槽的矩形。本文中若出现 `wrap_text` / `fit` / `密集档` / `textLength` 等提法，属于**迁移前的历史机制**，现已删除或不再参与判定；详见 [architecture.md 的《文字排版：为什么是 DOM》](architecture.md)。

## 1. 写 layout 函数（`scripts/ink.py`）

在 `LAYOUTS = {` **之前**插入函数（顺序要紧：字典引用函数名，函数必须先定义）。
参照 `layout_chain` 这类 SVG 版式，或 `layout_bullets` 这类 HTML 版式。

```python
def layout_pyramid(card, seed):
    """金字塔：N 层从宽到窄堆叠，每层一个要点。"""
    levels = card.get("levels", [])
    pal = Palette(seed)
    n = max(2, min(5, len(levels)))
    avail = 900
    bx = BOX_INSET
    parts = [defs("a0")]
    for i, lv in enumerate(levels[:n]):
        w = int((W_INNER - 2 * bx) * (1 - i * 0.16))     # 越往上越窄
        x = bx + (W_INNER - 2 * bx - w) / 2
        y = 80 + i * 150
        fill = PAL.get(lv.get("fill")) or pal.next()
        parts.append(pen_box(x, y, w, 120, i * 13 + 5, fill))
        parts.append(hl_line(W_INNER / 2, y + 72,
                             parse_hl(lv.get("text", ""), pal, plain=bool(fill)),
                             44, i * 7 + 3, maxw=w - 40))
    if card.get("note"):
        parts.append(txt_block(W_INNER / 2, avail - 40, strip_hl(card["note"]),
                               SIZES["note"], W_INNER, max_lines=1, tag="pyr-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))
```

★ 新增版式时，**每个文字槽位都必须通过 `txt()` / `hl_line()` / `txt_block()` /
`_inline()` 落字** —— 这四个函数会自动把净文本登记进内容门。如果你直接拼
`"<text ...>%s</text>" % esc(...)`，那段文字就绕过了登记，内容门对它**失明**
（matrix 的竖排轴标签、bullets 的已上色行就是这么补登记的）。

另外注意 `txt_block()` 登记的是**折行前的原文**——这样引擎把长文案折算成「…」时，
内容门会因为"尾巴没出现在图上"而报 `missing-text`（顺带在 build 阶段打一条"文案被截断"的 WARN）。
你自己写多行渲染时，也要登记原始串，别登记已折好的行。

**必须遵守的约定**（否则三道门会失效）：

| 约定 | 为什么 |
|---|---|
| 用 `pen_box()` 画框 | 它会往 `_BOXES` 注册方框，`measure.py` 靠这个清单判断"文字是否压框" |
| 文字用 `hl_line()` / `txt()` / `txt_block()` | 它们带宽度预算；`tw()` 会乘实测校准因子 |
| 上色的框内文字传 `plain=bool(fill)` | 避免色带和框色打架（引擎统一规则） |
| 内容高度 ≤ `avail` | 画到画布外会被静默裁掉 |
| 方框用 `BOX_INSET` 内缩 | 描边有 3px 半宽，贴画布边会被裁一半 |

## 2. 注册到 `LAYOUTS` 字典

```python
LAYOUTS = {
    ...
    "pyramid": layout_pyramid,
    ...
}
```

**改完立刻验证**（这一步别省，我曾因为漏了它导致新版式静默不生效）：

```bash
python -c "import sys; sys.path.insert(0,'scripts'); import ink; print(len(ink.LAYOUTS), list(ink.LAYOUTS))"
```

## 3. 加字数契约（`templates/contracts.yaml`）

**用真实渲染过的样张定标**，别拍脑袋：

```yaml
  pyramid:
    title: {min: 3, max: 14}
    subtitle: {max: 22}
    note: {max: 44, soft: true}
    levels:
      count: {min: 2, max: 5}
      fields:
        text: {max: 15}
```

判断软硬的实测方法：故意造一张超限页——
DOM 文字下，折行/行数/缩放由浏览器负责，所以槽的字数上限都是**建议值**（`soft: true` 的语义）；
真正会报硬问题的只有"缩到下限仍放不下"（`dom-overflow`）。

## 4. 加进方案图鉴（`make_layout_gallery.py`）

`GALLERY` 列表里加一条真实内容的样张，然后：

```bash
python make_layout_gallery.py -o gallery-out
```

看一眼新样张——**图鉴是"每个版式都能渲染"的回归测试**，也是一眼看出画歪的地方。

## 5. 同步文档（这一步最容易被跳过）

- `docs/layouts.md`：加一节（字段表 + 预算 + 什么时候用）
- `SKILL.md` 的版式表：加一行
- `README.md` / `README.en.md` 的版式表：加一行
- `docs/images/layouts/`：放一张样张

**没同步文档 = 文档有洞**，下个 Agent 会照着过时信息干活（这事真的发生过）。

## 自检清单

```bash
python -c "import sys; sys.path.insert(0,'scripts'); import ink; assert 'pyramid' in ink.LAYOUTS"
python scripts/validate.py examples/json/agent-roadmap.json   # 契约没被改坏
python make_layout_gallery.py -o gallery-out && ls gallery-out | grep pyramid
python scripts/pipeline.py examples/json/agent-roadmap.json -o build/chk   # 全流程回归
```

四条都过，才算加完。

> **如果你的版式想让页头闭嘴**（自己把标题画进 stage，像 `cover_title` / `cover_quote`
> 那样占满整页）：把它加进 `ink.HEADERLESS` 集合，然后**自己 `_reg_slot` 登记标题文字**
> —— 页头那支 `h1_html` 是唯一会 `_reg_text(标题)` 的地方，抑制了它而不同步登记，
> 内容门就会报 `missing-text`。`avail` 取 `_cover_avail()`（= 整卡内高 − 边距）。

---

## 加一种新版式：只画墨迹，文字登记成"槽"

文字**不要**自己算折行，也不要画 SVG `<text>`。照 `layout_flow` / `layout_chain` / `layout_compare` 写：

```python
def layout_mine(card, seed):
    parts = [defs("a0")]
    for i, it in enumerate(card.get("items", [])):
        x, y, w, h = 8, 100 + i * 120, 808, 100
        parts.append(pen_box(x, y, w, h, seed + i, pal.next()))       # 墨迹：方框
        # 文字：只给"容器矩形"，折行/居中/缩放交给浏览器
        _reg_slot(x + 16, y + 10, w - 32, h - 20, it.get("text", ""),
                  SIZES["body"], clamp=2, min_size=20)
    return "<svg class='stage' …>%s</svg>" % "".join(parts)
```

`_reg_slot(x, y, w, h, text, size, clamp=2, align="center", min_size=15, weight=None)`

| 参数 | 含义 |
|---|---|
| `x, y, w, h` | 文字**容器的矩形**（不是基线位置；浏览器在框内折行并垂直居中） |
| `size` | 起手字号；放不下时 autofit 会往下缩到 `min_size` |
| `clamp` | 最多几行（单行槽传 1） |
| `min_size` | 字号下限，一般取 `size` 的 0.5~0.6 |
| `align` | 默认居中；左对齐传 `"start"` |

两条纪律：
1. **框已上色时用 `strip_hl(...)`** 去掉 `[[高亮]]`（色带与框色打架）；未上色时保留 `[[…]]`，DOM 侧会画蜡笔底色
2. 不要调用 `txt` / `txt_block` / `hl_line` 画正文 —— 它们是旧路径，正在退役

**第三条（2026 加主题系统时补）**：**上色方框里的文字不要写死颜色**。
`_reg_slot` 不传 `color` 时会自动看一眼"这段字是不是落在某个已上色方框里"，
按填充色亮度选深字/浅字（`ink._ink_on`）—— 你只要保证**先 `pen_box` 再 `_reg_slot`**，
这条就自动生效。写了 `color=` 反而会盖掉它，除非你确实要一个固定色。

`color` 参数只有一种正当用法：**需要区别于正文色**的小标签（封面 kicker、金句出处）。

加完版式后跑 `python scripts/run.py <spec.json> --out <目录>`，exit=0 即可。

---

## 加一种新皮肤（比加版式简单得多）

往 `scripts/theme.py` 的 `THEMES` 加一条字典，**`ink.py` 一个字都不用改**（除非要加新的
高亮形态或 CSS 钩子）。**先想清楚属于哪个族**：

- `paper` 纸张族 —— 节点是**上色方框**，强调靠整块底色。
- `diagram` 工程族 —— 节点是**透明底 + 主题色细描边，无笔锋笔触**，
  强调默认是**四角刻度**（`node_style: corner`，每角一对短线）。
  令牌：`node_line`（留空=用 ink）/ `node_w` / `node_radius` / `node_style` / `tab_size`。
  三条硬规矩写在 `theme.py` 的模块 docstring 里 —— 尤其第一条：**底色要真透明**
  （`node_surface` 留空 → `fill='none'`），填一层"比底色亮一点的面"就看不到网格透进框里了。
  调外观别硬猜：`python make_style_probe.py`（列=皮肤，行=方框方案）。

令牌字段表与六条纪律在 `theme.py` 的模块 docstring 里。
加完 `python make_theme_gallery.py --family paper` 看图、`python tests/run.py` 跑回归。

## 改版式时的一条新纪律：用 `node_box`，不要用 `pen_box`

`pen_box` 是**纸张族**的画法（手绘上色方框）。版式里要画节点一律走 `node_box()` ——
它按 `theme.family` 分派：纸张族 = 上色方框，工程族 = 细描边 + 强调轨。
版式只说"这里有个节点、强调色是哪个"，**由族决定怎么画**。

同理：

| 要画 | 用 | 不要用 |
|---|---|---|
| 节点方框 | `node_box(x, y, w, h, seed, accent)` | `pen_box(..., fill)` |
| 节点圆点（timeline/cycle） | `node_dot(cx, cy, r, accent)` | 手写 `<circle fill=...>` |
| 节点椭圆（hub 中心） | `node_ellipse(...)` | 手写 hellipse + pen_box |
| 节点多边形（pyramid 梯形） | `node_poly(pts, seed, accent)` | `_poly_fill` + `pen_poly` |
| 光谱轴（spectrum） | `spectrum_bar(...)` | `grad_arrow(...)` |
| 取规格里的 `fill` | `pick_fill(v, pal)` | `PAL.get(v) or pal.next()` |
| 判"要不要剥高亮" | `fill_plain(fill)` | `bool(fill)` |

`pick_fill` 和 `fill_plain` 这两条是**修 bug 修出来的**：前者保证 `fill: none` 真的
不上色（`or` 写法会让它照样上色），后者保证工程族不因为"规格写了 fill"就把高亮全剥掉。
