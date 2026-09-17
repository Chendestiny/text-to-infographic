# 扩展：加一种新版式

以加一个 `pyramid`（金字塔）版式为例。**五步，缺一步就会被后续维护卡住。**

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

**必须遵守的约定**（否则两道门会失效）：

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
**真溢出**（被裁 / 压框）就是硬约束；**只是变密**（自动换行/缩字）就加 `soft: true`。

## 4. 加进方案图鉴（`make_layout_gallery.py`）

`GALLERY` 列表里加一条真实内容的样张，然后：

```bash
python make_layout_gallery.py -o gallery-out
```

看一眼新样张——**图鉴是"每个版式都能渲染"的回归测试**，也是一眼看出画歪的地方。

## 5. 同步文档（这一步最容易被跳过）

- `docs/layouts.md`：加一节（字段表 + 预算 + 什么时候用）
- `SKILL.md` 的版式表：加一行
- `README.md` / `README.zh-CN.md` 的版式表：加一行
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
