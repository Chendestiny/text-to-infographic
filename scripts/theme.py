# -*- coding: utf-8 -*-
"""theme.py —— 主题（皮肤）注册表

**一个主题 = 一组设计令牌**，不碰版式逻辑。版式只管"哪里放什么"，主题决定
"它长什么样"：底色 / 描边色 / 文字色 / 6 色调色板 / 笔锋抖动 / 线宽 / 高亮形态 /
圆角影子 / 装饰件 / 额外 CSS。

为什么把令牌抽出来而不是复制一份 ink.py：
  15 个版式 × 6 套皮肤 = 90 份手写样式，改一次字号要改 90 处。
  抽成令牌之后，加一套皮肤只需要往 THEMES 里加一条字典 —— **ink.py 一个字都不用动**
  （除非要加一种新的高亮形态或新的 CSS 钩子）。

## ★ 两个族（`family`）—— 这是这一层最重要的概念

皮肤分两类，**视觉语言根本不同**，不是"换个颜色"：

| 族 | 谁 | 节点怎么画 | 重音怎么给 | 状态 |
|---|---|---|---|---|
| `paper` 纸张族 | crayon 蜡笔纸感 / grid 方格稿纸 / retro 复古报刊 | 手绘笔锋 + **上色方框**（蜡笔涂块） | 整块底色 | **已定稿** |
| `diagram` 工程族 | terminal 暗夜终端 / blueprint 工程蓝图 / mono 素白细线 / nord 北欧冷调 | **透明底 + 主题色细描边，无笔锋笔触** | 四角各一对短刻度 | **版式仍在调整** |

踩过的坑：一开始只做了"换颜色"，把纸张族那套高饱和方框填色直接套到工程风上 ——
结果暗夜终端里一块块荧光色填充块，跟"工程图"这个语义完全打架。
正解不是调色，而是**把"节点"这个原语本身做成族的职责**（`ink.node_box`），
版式只管"这里有个节点、它该用哪个强调色"，由族决定怎么画。

### 工程族的节点口径（用户 2026 定的三条）

1. **框的背景透明**，就是和底色一致 —— `node_surface` 留空 → `fill='none'`。
   ★ 不是"填一个比底色亮一点的面的色"：前者**网格会透进框里**，后者不会，
   在蓝图/终端那套坐标网格上，差别一眼就看得出来。
2. **边框是黑色或主题色** —— `node_line` 留空就用 `ink`。
   别塞低饱和中间色（我一开始取 `#33415E` 那种，结果整页灰蒙蒙没有"图纸感"）。
3. **没有笔锋笔触** —— 画的是精确 `<rect>`，不走 `pen_rect` 那套"一条边拆 4 段收笔"。

那一处强调由 `node_style` 选形态（`tab` 左上角块 / `rail` 左侧竖轨 / `rule` 顶边短线 /
`double` 内外双线框 / `corner` 四角刻度 / `none` 不画）。
**现在默认 `corner`（四角刻度）** —— 它给每个节点一个"取景框"，四角同色、
一眼能数清几步；比过 `tab`（彩色小方块，也好看但更像"端子"）、
`rail`（在 bullets 那种整行上偏重）、`rule`（落在文字旁边像多画一笔）。
六种都实现好了，换一个令牌即可，**比选命令**：
`python make_style_probe.py`（列=皮肤，行=方案，出到桌面 `t2i-box-styles/`）。

> 工程族的节点渲染路径已经实现并可用，但**它的版式还在重做**（这类皮肤要的是
> 更工程化的排版语言，不是把纸张版式换个色），所以暂时不进 README 与正式图鉴。
> 想看现状：`python make_theme_gallery.py --family diagram -o out/diagram`。

## 令牌字段

| 字段 | 含义 | 缺省 |
|---|---|---|
| label / en / desc | 中文名 / 英文名 / 一句话（`--themes` 列出来给人挑） | 必填 |
| **family** | `paper` / `diagram`，决定节点原语（见上） | paper |
| bg_page / bg_card | 页面底 / 卡片底 | 必填 |
| box | 不上色方框的填充（工程族就是节点底色） | 必填 |
| ink | 墨迹描边色（方框/箭头/外框） | 必填 |
| head / text / note / foot | 主标题 / 正文 / 注释 / 页脚 | 必填 |
| pal | 6 色调色板，键必须齐 `blue/yellow/pink/green/gray/orange` | 必填 |
| order | 调色板轮换顺序（默认蓝→黄→粉→绿→灰→橙） | 默认顺序 |
| wobble | 手绘抖动倍率。**0 = 直线**（工程族全是 0），1 = 现在的手绘笔锋 | 1.0 |
| over | 出锋倍率（线头长出端点多少）。不传则跟随 wobble | = wobble |
| sw | 线宽倍率 | 1.0 |
| cap | 线帽 `round` / `butt` / `square` | round |
| font | 覆盖字体栈（终端/蓝图用等宽） | 系统 CJK 栈 |
| hl | 高亮形态：`crayon` / `flat` / `block` / `underline` | crayon |
| hl_ink | 高亮块上的文字色（`block` 形态用） | 跟随 head |
| ink_on_light | 亮色填充上该写的深色（按亮度自动选用，见 `ink._ink_on`） | 跟随 text |
| radius / radius_round | 方框圆角 / 卡片圆角 | 8 / 28 |
| shadow | 卡片投影 | 无 |
| row_border | `.row`（bullets 行）的边框宽度 | 5.6 |
| frame | **默认外框**（spec 没写 meta.frame 时用它） | pen |
| accent / kicker | 色条色 / 左上角小标签色（不写就按调色板轮换） | 无 |
| deco / decos / deco_scale | 是否画装饰 / 零件清单 / 尺寸倍率 | True / 齿轮星云 / 1.0 |
| css | 额外 CSS，追加在基础 CSS 之后（可以覆盖任何规则） | 空 |

**只有 `family: diagram` 会用到的节点令牌**：

| 字段 | 含义 |
|---|---|
| node_surface | 节点底色。**留空 = 透明**（用户口径：框的背景和底色一致，网格能透进框里） |
| node_line | 节点描边色。留空 = 用 `ink`（黑色或主题色）—— 不要塞低饱和中间色 |
| node_w | 节点描边宽度（1.2~1.8，工程图要细） |
| node_radius | 节点圆角 |
| node_style | 那一处强调的形态：`tab` 左上角实心块 / `rail` 左侧竖轨 / `rule` 顶边短线 / `double` 内外双线框 / `corner` 四角刻度 / `none` 不画 |
| rail_w / rail_frac | `rail` 的宽度 / 高度占节点高的比例 |

## 加一套皮肤的纪律

1. **先想清楚属于哪个族**：靠"色块"表达层级 → paper；靠"线 + 一小段色"表达 → diagram。
   新皮肤跟着已有的族走就行，两条族的渲染路径都已经在 `ink.node_box` 里实现了。
2. **颜色要成套给**，别只改 ink 不改 pal —— 深底上留一套浅色蜡笔会像贴纸。
3. **`wobble: 0` 的主题要同时把 `sw` 收到 0.4~0.6**：直线 + 6px 线宽 = 水桶腰。
4. **深色主题必须核对 `note`**：页脚注释最容易被忘掉，深底 + `#4A4A4A` 是看不见的。
5. **工程族的 `pal` 是"强调色"不是"填充色"**：它只出现在细轨、下划线、描边上，
   所以可以高饱和（一根 5px 的荧光绿轨很好看，一整块荧光绿填充很丑）。
6. 加完跑 `python make_theme_gallery.py` 看图，再跑 `python tests/run.py`。
"""

DEFAULT = "crayon"


def _pal(blue, yellow, pink, green, gray, orange):
    """6 色调色板。键名固定（`[[x|b]]` 这类缩写靠它反查），只换值。"""
    return {"blue": blue, "yellow": yellow, "pink": pink,
            "green": green, "gray": gray, "orange": orange}


# ---------------------------------------------------------------- 高亮形态
# `[[关键词]]` 在 DOM 侧是 `<span class="hl X">`，底色由 .hl::before 画。
# 这几种形态决定了"高亮"长什么样 —— 蜡笔色带 / 半透明色块 / 实心色块 / 粗下划线。
HL_STYLES = {
    # 蜡笔色带：多道错位斜纹模拟蜡笔涂写，微微倾斜（与 SVG 时代视觉一致）
    "crayon": """
.hl{position:relative;display:inline-block;padding:7px 12px;z-index:0;font-weight:700;}
.hl::before{content:'';position:absolute;left:-6px;right:-6px;top:14%;bottom:-4%;z-index:-1;
  border-radius:4px 8px 5px 9px;transform:rotate(-.8deg);
  background-image:
    repeating-linear-gradient(-1.6deg, rgba(255,255,255,0) 0 5px, rgba(110,100,70,.10) 5px 8px),
    repeating-linear-gradient(1.1deg, rgba(255,255,255,0) 0 9px, rgba(255,255,255,.20) 9px 13px);}
""",
    # 半透明色块：终端/北欧这类深底用。不做斜纹（深底上斜纹会变脏）
    # ★ 透明度由 `hl_alpha` 给：深底上 0.30 会糊成橄榄色，工程族收到 0.22
    "flat": """
.hl{position:relative;display:inline-block;padding:5px 10px;z-index:0;font-weight:700;}
.hl::before{content:'';position:absolute;left:-3px;right:-3px;top:4%;bottom:4%;z-index:-1;
  border-radius:8px;opacity:%HL_ALPHA%;}
""",
    # 实心色块：野兽派。块上是黑字，所以 head 必须是深色
    "block": """
.hl{position:relative;display:inline-block;padding:4px 12px;z-index:0;font-weight:800;
    color:%HL_INK%;}
.hl::before{content:'';position:absolute;left:-6px;right:-6px;top:0;bottom:0;z-index:-1;
  border-radius:0;}
""",
    # 粗下划线：极简/蓝图。不挡字，最克制
    "underline": """
.hl{position:relative;display:inline-block;padding:0 3px;z-index:0;font-weight:700;}
.hl::before{content:'';position:absolute;left:-2px;right:-2px;bottom:-1px;height:9px;
  z-index:-1;border-radius:2px;opacity:.55;}
""",
}

# 色块颜色按调色板键轮流给（`.hl.y::before` 这类）
HL_COLORS = """
.hl.y::before{background-color:%PAL_Y%}
.hl.b::before{background-color:%PAL_B%}
.hl.p::before{background-color:%PAL_P%}
.hl.g::before{background-color:%PAL_G%}
.hl.gr::before{background-color:%PAL_GR%}
.hl.o::before{background-color:%PAL_O%}
"""

# 终端/蓝图共用：网格底纹。用多重 background layer，一条 grid + 几条零散亮格
# （参考图里就是这样：细网格 + 几块随机加深的格子，比纯网格有生气）
_GRID_DARK = """
/* 网格底纹：主格 + 四块零散亮格（参考图上那种"随手点亮的格子"） */
.card{background-image:
  linear-gradient(rgba(120,210,255,.030),rgba(120,210,255,.030)),
  linear-gradient(rgba(120,210,255,.030),rgba(120,210,255,.030)),
  linear-gradient(rgba(120,210,255,.030),rgba(120,210,255,.030)),
  linear-gradient(rgba(120,210,255,.026) 1px,transparent 1px),
  linear-gradient(90deg,rgba(120,210,255,.026) 1px,transparent 1px);
  background-size:72px 72px,72px 72px,72px 72px,72px 72px,72px 72px;
  background-position:216px 504px,504px 216px,360px 864px,0 0,0 0;
  background-repeat:no-repeat,no-repeat,no-repeat,repeat,repeat;}
"""


THEMES = {}

# ══════════════════════════════════════════════════════════════════════════
# 第 1 类 · 纸张族（复用现有版式）—— crayon / grid / retro
#   节点 = 手绘上色方框，强调靠整块底色。这三套**已经定稿**。
#   第 2 类 · 工程族（diagram）—— terminal / blueprint / mono / nord
#   节点 = 细描边 + 左侧强调轨，**版式仍在调整**，暂不进 README 与正式图鉴。
#   预览：python make_theme_gallery.py --family diagram -o out/diagram
# ══════════════════════════════════════════════════════════════════════════

# ─────────────────────────────────────────────── 1. 蜡笔纸感（现有皮肤，默认）
THEMES["crayon"] = {
    "label": "蜡笔纸感", "en": "Crayon Paper",
    "desc": "米黄纸底 + 暖灰手绘笔锋 + 蜡笔色带。手账感，最抗「AI 味」。",
    "bg_page": "#E7E3D4", "bg_card": "#FAF7EF", "box": "#FDFAF0",
    "ink": "#5C584F", "head": "#141414", "text": "#1F1F1F",
    "note": "#4A4A4A", "foot": "#9A9A96",
    "pal": _pal("#7FCBEF", "#FFE04D", "#F79BB0", "#9FE0B8", "#CFCBC0", "#FFC48C"),
    "wobble": 1.0, "over": 1.0, "sw": 1.0, "cap": "round",
    "hl": "crayon",
    "radius": 8, "radius_round": 28, "shadow": "0 6px 26px rgba(0,0,0,.07)",
    "row_border": 5.6, "frame": "pen", "accent": None, "deco_scale": 1.0,
    "decos": ["gear1", "gear2", "star4", "star5", "star5f", "cloud"],
}

# ─────────────────────────────────────────────── 2. 暗夜终端（参照图同款）
# ★ 工程族（第 2 类）：**版式仍在调整**，暂不进 README 与正式图鉴。
#   节点用「细描边 + 左侧强调轨」表达，不做高饱和方框填色 —— 见 ink.node_box。
THEMES["terminal"] = {
    "label": "暗夜终端", "en": "Terminal",
    "desc": "深藏蓝底 + 荧光绿细线 + 网格，等宽字。节点透明底 + 四角刻度。",
    "family": "diagram",
    "bg_page": "#080B14", "bg_card": "#0E1422", "box": "#151D30",
    "ink": "#2EE87F", "head": "#F4F8FF", "text": "#C6D2E6",
    "note": "#8496B4", "foot": "#5C6A86",
    "pal": _pal("#4FD8E8", "#FFC94D", "#FF7A9C", "#2EE87F", "#56637F", "#FF9F45"),
    "wobble": 0.0, "sw": 0.42, "cap": "butt",
    "font": "'JetBrains Mono','Cascadia Mono',Consolas,'SF Mono',"
            "'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',monospace",
    "hl": "flat", "hl_alpha": 0.22,
    "radius": 0, "radius_round": 0, "shadow": "none",
    "row_border": 2, "frame": "none",
    "node_surface": None, "node_line": None, "node_w": 2.2,
    "node_radius": 8, "node_style": "corner", "tab_size": 20, "rail_w": 5, "rail_frac": 0.5,
    "accent": "#2EE87F", "kicker": "#2EE87F", "deco_scale": 1.5,
    "ink_on_light": "#0B1220",
    "decos": ["plus3", "pixq", "crosshair"],
    "css": _GRID_DARK,
}

# ─────────────────────────────────────────────── 3. 工程蓝图
THEMES["blueprint"] = {
    "label": "工程蓝图", "en": "Blueprint",
    "desc": "深蓝底 + 冷白细线 + 双层坐标网格。节点透明底 + 四角刻度，最像工程图纸。",
    "family": "diagram",
    "bg_page": "#0A2137", "bg_card": "#0E2B48", "box": "#123252",
    "ink": "#7FC4EE", "head": "#FFFFFF", "text": "#D7E9F7",
    "note": "#8FB6D2", "foot": "#5E86A6",
    "pal": _pal("#6FB8FF", "#FFD166", "#FF8FA3", "#5FE3C0", "#5A7E9E", "#FFA65C"),
    "wobble": 0.0, "sw": 0.4, "cap": "round",
    "hl": "underline",
    "radius": 0, "radius_round": 4, "shadow": "none",
    "row_border": 2, "frame": "card", "accent": "#6FE3FF",
    "kicker": "#6FE3FF", "deco_scale": 1.4,
    "node_surface": None, "node_line": None, "node_w": 2.0,
    "node_radius": 4, "node_style": "corner", "tab_size": 18, "rail_w": 4, "rail_frac": 0.5,
    "ink_on_light": "#08243C",
    "decos": ["crosshair", "corners", "plus3"],
    "css": """
.card{background-image:
  linear-gradient(rgba(160,215,255,.09) 1px,transparent 1px),
  linear-gradient(90deg,rgba(160,215,255,.09) 1px,transparent 1px),
  linear-gradient(rgba(160,215,255,.035) 1px,transparent 1px),
  linear-gradient(90deg,rgba(160,215,255,.035) 1px,transparent 1px);
  background-size:120px 120px,120px 120px,24px 24px,24px 24px;}
""",
}

# ─────────────────────────────────────────────── 4. 方格稿纸
THEMES["grid"] = {
    "label": "方格稿纸", "en": "Grid Paper",
    "desc": "浅米底 + 淡蓝方格 + 蓝黑墨水。像写在数学本上，学生 / 笔记向。",
    "bg_page": "#D9D5C8", "bg_card": "#FCFAF3", "box": "#FFFDF8",
    "ink": "#33445C", "head": "#17202E", "text": "#232D3C",
    "note": "#5B6878", "foot": "#8C97A6",
    "pal": _pal("#9CCDE8", "#FFE9A8", "#F5B9C6", "#B2DFC2", "#DAD6CA", "#FFD3A8"),
    "wobble": 0.25, "sw": 0.65, "cap": "round",
    "hl": "flat", "hl_alpha": 0.22,
    "radius": 6, "radius_round": 14, "shadow": "0 4px 16px rgba(30,40,60,.08)",
    "row_border": 4, "frame": "card", "accent": None, "kicker": None,
    "deco_scale": 1.0, "ink_on_light": "#232D3C",
    "decos": ["star4", "star5", "gear1"],
    "css": """
.card{background-image:
  linear-gradient(rgba(90,140,190,.13) 1px,transparent 1px),
  linear-gradient(90deg,rgba(90,140,190,.13) 1px,transparent 1px);
  background-size:36px 36px,36px 36px;}
""",
}

# ─────────────────────────────────────────────── 5. 素白细线
THEMES["mono"] = {
    "label": "素白细线", "en": "Mono Swiss",
    "desc": "白底 + 黑细线，只有描边没有装饰件，留白最狠的一支，适合严肃观点。",
    "family": "diagram",
    "bg_page": "#E8E8E6", "bg_card": "#FFFFFF", "box": "#FCFCFC",
    "ink": "#141414", "head": "#000000", "text": "#1C1C1C",
    "note": "#5E5E5E", "foot": "#9A9A9A",
    "pal": _pal("#2F6BFF", "#F2C94C", "#FF7A9C", "#4FBF8B", "#BDBDBD", "#FF9A3D"),
    "order": ["gray", "yellow", "pink", "green", "orange", "blue"],
    "wobble": 0.0, "sw": 0.28, "cap": "butt",
    "hl": "underline",
    "radius": 2, "radius_round": 4, "shadow": "none",
    "row_border": 1.2, "frame": "card", "accent": "#2F6BFF",
    "kicker": "#2F6BFF", "deco_scale": 1.0,
    "node_surface": None, "node_line": None, "node_w": 1.7,
    "node_radius": 3, "node_style": "none", "tab_size": 14, "rail_w": 0, "rail_frac": 0.5,
    "ink_on_light": "#1C1C1C",
    "decos": [],
}

# ─────────────────────────────────────────────── 6. 复古报刊
THEMES["retro"] = {
    "label": "复古报刊", "en": "Retro Print",
    "desc": "米黄报纸底 + 深褐墨水 + 粗下划线。像剪报，适合观点 / 书评。",
    "bg_page": "#D8CBAF", "bg_card": "#F4EAD4", "box": "#F9F1E0",
    "ink": "#4A3A26", "head": "#241A10", "text": "#382C1C",
    "note": "#6A5940", "foot": "#9C8A6E",
    "pal": _pal("#7E96B0", "#E0B75C", "#C97B5A", "#9AAE7E", "#D8C4A0", "#B4553A"),
    "wobble": 0.55, "sw": 0.85, "cap": "round",
    "hl": "underline",
    "radius": 0, "radius_round": 0, "shadow": "none",
    "row_border": 5, "frame": "pen", "accent": None, "kicker": None,
    "deco_scale": 1.0, "ink_on_light": "#382C1C",
    "decos": ["star4", "star5", "gear1"],
    "css": """
.card{background-image:
  repeating-linear-gradient(0deg, rgba(120,95,55,.035) 0 2px, transparent 2px 5px);}
""",
}

# ─────────────────────────────────────────────── 7. 北欧冷调
THEMES["nord"] = {
    "label": "北欧冷调", "en": "Nord",
    "desc": "深灰蓝底 + 极地色系（霜蓝/极光绿/紫）。暗色但柔，长时间看不累。",
    "family": "diagram",
    "bg_page": "#242933", "bg_card": "#2E3440", "box": "#3B4252",
    "ink": "#88C0D0", "head": "#ECEFF4", "text": "#D8DEE9",
    "note": "#9AA7BB", "foot": "#6D788E",
    "pal": _pal("#88C0D0", "#EBCB8B", "#B48EAD", "#A3BE8C", "#4C566A", "#D08770"),
    "wobble": 0.0, "sw": 0.45, "cap": "round",
    "hl": "flat", "hl_alpha": 0.22,
    "radius": 8, "radius_round": 24, "shadow": "none",
    "row_border": 2, "frame": "card", "accent": "#88C0D0",
    "kicker": "#88C0D0", "deco_scale": 1.2,
    # 用户口径：纯细线，不要四角刻度；细线**加粗到 2 倍**（2.4 → 4.8）——
    # 北欧冷调底色偏灰，2.4px 在它上面太飘，读起来像没画框
    "node_surface": None, "node_line": None, "node_w": 4.8,
    "node_radius": 8, "node_style": "none", "tab_size": 20, "rail_w": 5, "rail_frac": 0.5,
    "ink_on_light": "#2E3440",
    "decos": ["crosshair", "corners", "plus3"],
    "css": """
/* 极淡的图纸网格：工程族四套成套（素白细线那套除外，它要的是"素白"） */
.card{background-image:
  linear-gradient(rgba(136,192,208,.05) 1px,transparent 1px),
  linear-gradient(90deg,rgba(136,192,208,.05) 1px,transparent 1px);
  background-size:64px 64px,64px 64px;}
""",
}


# ---------------------------------------------------------------- 读取
_FIELDS_DEFAULT = {
    "order": ["blue", "yellow", "pink", "green", "gray", "orange"],
    "wobble": 1.0, "sw": 1.0, "cap": "round", "font": None,
    "hl": "crayon", "hl_ink": None, "hl_alpha": 0.30,
    "radius": 8, "radius_round": 28, "shadow": "none", "row_border": 5.6,
    "frame": "pen", "deco": True, "decos": ["gear1", "star4", "cloud"],
    "accent": None, "kicker": None, "deco_scale": 1.0, "ink_on_light": None,
    # 族与节点外观：paper = 手绘上色方框；diagram = 透明底 + 细描边 + 一处强调
    "family": "paper",
    "node_surface": None, "node_line": None, "node_w": 1.6,
    "node_radius": 6, "node_style": "rail", "tab_size": 20, "rail_w": 0, "rail_frac": 0.5,
    "tab_size": 20,
    "css": "",
}


def get(name):
    """取一个主题的**补全后**令牌（缺省字段已填好）。名字不认识就报错，别静默回落。

    为什么不静默回落：写错 `"terminal "`（带空格）时如果悄悄用默认皮肤，
    用户会以为"这个主题就这样"，而实际是名字没匹配上 —— 属于最难查的一类问题。
    """
    key = (name or DEFAULT).strip()
    if key not in THEMES:
        raise KeyError("未知主题 %r（可用：%s）" % (name, ", ".join(names())))
    t = dict(_FIELDS_DEFAULT)
    t.update(THEMES[key])
    t["key"] = key
    t.setdefault("over", t["wobble"])          # 出锋默认跟随抖动：直线主题不该有出锋
    if t["hl_ink"] is None:
        t["hl_ink"] = t["head"]
    if t["ink_on_light"] is None:      # 没给就跟随正文色（浅色主题就是这个语义）
        t["ink_on_light"] = t["text"]
    # 工程族的节点外观兜底。★ 关键：`node_surface` **不兜底成卡片底色** ——
    # 留 None = `fill='none'`（真透明），用户口径是"框的背景和底色一致"，
    # 而"填一个比底色亮一点的面的色"完全不是一回事：前者网格会透进框里。
    if t["family"] == "diagram" and t["node_line"] is None:
        t["node_line"] = t["ink"]
    return t


def names():
    """全部主题 key，注册顺序（也是 `--themes` 的打印顺序）。"""
    return list(THEMES)


def catalog():
    """给 CLI 用的清单：[(key, label, en, desc), ...]"""
    return [(k, THEMES[k]["label"], THEMES[k]["en"], THEMES[k]["desc"]) for k in names()]


if __name__ == "__main__":
    print("主题（%d 套）：" % len(THEMES))
    for k, label, en, desc in catalog():
        mark = "  ← 默认" if k == DEFAULT else ""
        print("  %-12s %-6s %-14s %s%s" % (k, en, label, desc, mark))
