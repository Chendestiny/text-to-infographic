# -*- coding: utf-8 -*-
"""text-to-infographic · 渲染核心

设计原则
  1. **确定性**：同样的 cards 规格永远渲染出同样的图（所有抖动都用固定种子的 RNG）
  2. **规格与像素分离**：Agent 只负责产出 cards 规格（讲什么、怎么排），本文件负责所有像素
  3. **零第三方依赖**：只用标准库。YAML 规格需要 pyyaml，JSON 规格不需要
  4. **跨平台**：字体栈覆盖 Windows / macOS / Linux，不写死任何系统字体

坐标体系
  整卡 1008×1368（3:4 的 1080×1440 去掉 36px 外边距），内边距上 96 / 左右 92，
  内容可用宽 824。任何画到画布外的东西都会被 overflow:hidden 静默裁掉，所以
  每个 layout 都自己保证内容高度不超过 1246。
"""
import json
import math
import os
import random
import re

# ---------------------------------------------------------------- 画布与主题
W_CARD, H_CARD = 1008, 1368
MARGIN = 36
PAD_X, PAD_TOP = 92, 96
W_INNER = W_CARD - PAD_X * 2          # 824
H_SAFE = H_CARD - PAD_TOP - 120       # 内容安全高度（留标题区与页脚）

INK = "#5C584F"                        # 手绘描边（暖灰，不抢戏）
SW_LINE = 6.0                          # 手绘线宽
SW_ARROW = 5.6                         # 箭头线宽

BG_PAGE = "#E7E3D4"
BG_CARD = "#FAF7EF"
BOX = "#FDFAF0"                        # 不上色的方框
BOX_INSET = 8                         # ★ 方框统一内缩：描边有 3px 半宽，贴着画布边会被裁掉一半
PAL = {"yellow": "#FFE04D", "blue": "#7FCBEF", "pink": "#F79BB0",
       "green": "#9FE0B8", "orange": "#FFC48C", "gray": "#CFCBC0"}
C_HEAD = "#141414"
C_TEXT = "#1F1F1F"
C_NOTE = "#6F6F6F"

# 字体栈：带一套跨三平台的中文无衬线回退，不写死系统字体
FONT_SANS = ("'PingFang SC','Microsoft YaHei','Noto Sans CJK SC',"
             "'Source Han Sans SC','Hiragino Sans GB',Arial,sans-serif")
FONT_EMOJI = "'Apple Color Emoji','Segoe UI Emoji','Noto Color Emoji'"

SIZES = {"h1": 88, "sub": 42, "body": 52, "note": 38}

# 校准因子：tw() 是估算，真实渲染宽度由 measure 节点测出后回写到这里。
# 这是「measure → 修正 → 重建」反馈闭环的核心：估算器自己会变准。
CALIB = [1.0]
# 当前卡片的方框清单（pen_box 注册），build 时埋进 HTML 供 measure 比对
_BOXES = []

WARN = []


# ---------------------------------------------------------------- 随机与手绘原语
def _rnd(seed):
    return random.Random(seed)


def _unit(ax, ay, bx, by):
    dx, dy = bx - ax, by - ay
    L = (dx * dx + dy * dy) ** 0.5 or 1.0
    return dx / L, dy / L


def hand_line(ax, ay, bx, by, seed, seg=7, amp=2.2, over=5.0):
    """单条手绘折线（箭头、虚线、标注线用）。"""
    r = _rnd(seed)
    ux, uy = _unit(ax, ay, bx, by)
    nx, ny = -uy, ux
    o1, o2 = r.uniform(0, over), r.uniform(0, over)
    ax, ay = ax - ux * o1, ay - uy * o1
    bx, by = bx + ux * o2, by + uy * o2
    pts = []
    for i in range(seg + 1):
        t = i / float(seg)
        x, y = ax + (bx - ax) * t, ay + (by - ay) * t
        if 0 < i < seg:
            x += nx * r.uniform(-amp, amp)
            y += ny * r.uniform(-amp, amp)
        pts.append("%.1f %.1f" % (x, y))
    return "M" + " L".join(pts)


def pen_edge(ax, ay, bx, by, seed, w=SW_LINE, amp=1.0, over=(1.0, 5.0)):
    """一条带「笔锋」的手绘边：收笔处逐段变细变浅。

    相邻段必须重叠（a -= 0.018），否则渲染出来像线条断掉而不是收窄。
    """
    r = _rnd(seed)
    ux, uy = _unit(ax, ay, bx, by)
    nx, ny = -uy, ux
    o1, o2 = r.uniform(*over), r.uniform(*over)
    ax, ay = ax - ux * o1, ay - uy * o1
    bx, by = bx + ux * o2, by + uy * o2
    out = []
    # 收笔只在**最后 12~18%** 发生。
    # 踩过的坑：早先把 t_start 取在 0.50~0.70，等于半条边都在渐变，
    # 从 6px/100% 淡到 2.3px/58%，在正常缩放下看起来就是「线断了」。
    t_start = r.uniform(0.82, 0.88)
    spec = [(0.0, t_start, 1.0, 1.0, 1.0)]
    n = 3
    for i in range(n):
        a = t_start + (1 - t_start) * i / n
        b = t_start + (1 - t_start) * (i + 1) / n
        a = max(0.0, a - 0.012)          # 相邻段重叠，防止出现断口
        k = (i + 1) / float(n)
        spec.append((a, b, 1.0 - 0.58 * (k ** 1.8), 1.0 - 0.40 * (k ** 1.5), 0.40))
    for t0, t1, wf, op, af in spec:
        x0, y0 = ax + (bx - ax) * t0, ay + (by - ay) * t0
        x1, y1 = ax + (bx - ax) * t1, ay + (by - ay) * t1
        pts = []
        for i in range(5):
            t = i / 4.0
            x, y = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            if 0 < i < 4:
                x += nx * r.uniform(-amp * af, amp * af)
                y += ny * r.uniform(-amp * af, amp * af)
            pts.append("%.1f %.1f" % (x, y))
        out.append(("M" + " L".join(pts), w * wf, op))
    return out


def pen_rect(x, y, w, h, seed, amp=1.0, over=(1.0, 5.0)):
    """四条带笔锋的边，只负责描边。"""
    edges = [(x, y, x + w, y), (x + w, y, x + w, y + h),
             (x + w, y + h, x, y + h), (x, y + h, x, y)]
    out = []
    for i, (ax, ay, bx, by) in enumerate(edges):
        out += pen_edge(ax, ay, bx, by, seed * 31 + i, amp=amp, over=over)
    return out


def pen_path(segs, color=INK):
    return "".join("<path d='%s' fill='none' stroke='%s' stroke-width='%.2f' "
                   "stroke-opacity='%.2f' stroke-linecap='round' stroke-linejoin='round'/>"
                   % (d, color, w, op) for d, w, op in segs)


def hrect_path(x, y, w, h, seed, amp=1.8, seg=5):
    """★ 单条**闭合**手绘矩形 —— 只有闭合路径能真正被 fill 填充。

    踩过的坑：用四条独立开放折线拼框时，SVG 会隐式闭合每条子路径，
    而"一条线"的闭合面积≈0，fill 等于没涂，只有描边生效。
    """
    r = _rnd(seed + 991)
    edges = [((x, y), (x + w, y)), ((x + w, y), (x + w, y + h)),
             ((x + w, y + h), (x, y + h)), ((x, y + h), (x, y))]
    pts = []
    for (ax, ay), (bx, by) in edges:
        ux, uy = _unit(ax, ay, bx, by)
        nx, ny = -uy, ux
        for k in range(seg):
            t = k / float(seg)
            px, py = ax + (bx - ax) * t, ay + (by - ay) * t
            if k:
                px += nx * r.uniform(-amp, amp)
                py += ny * r.uniform(-amp, amp)
            pts.append((px, py))
    return "M" + " L".join("%.1f %.1f" % q for q in pts) + " Z"


def pen_box(x, y, w, h, seed, fill=None):
    """手绘方框：闭合路径负责填充，四条带笔锋的线负责描边。fill=None 表示不上色。"""
    _BOXES.append({"x": x, "y": y, "w": w, "h": h})
    d = hrect_path(x, y, w, h, seed)
    out = "" if not fill else "<path d='%s' fill='%s'/>" % (d, fill)
    return out + pen_path(pen_rect(x, y, w, h, seed))


def dash_box(x, y, w, h, seed, label=None, label_size=28):
    """虚线手绘框（可带标签）—— 装饰性容器，不填充。

    用途：把一组节点框成一个阶段（如「MCP：首尾那套传输」），
    或者在版式外围再包一层语义分区。
    """
    d = hrect_path(x, y, w, h, seed, amp=1.4, seg=6)
    out = ("<path d='%s' fill='none' stroke='%s' stroke-width='3' "
           "stroke-dasharray='14 10' stroke-linecap='round'/>" % (d, INK))
    if label:
        out += txt(x + w / 2, y + 30, label, label_size, fill=C_NOTE)
    return out


def crayon(cx, y, w, h, seed, color, passes=3):
    """蜡笔/马克笔涂写底色：多道略错位、端部不齐的半透明粗笔触叠出来。"""
    r = _rnd(seed + 7)
    x0 = cx - w / 2.0
    out = []
    for i in range(passes):
        a = x0 - r.uniform(2, 9)
        b = x0 + w + r.uniform(2, 9)
        yy = y - h * 0.5 + h * (i + 0.5) / passes + r.uniform(-2, 2)
        thick = (h / passes) * r.uniform(1.35, 1.6)
        mx = (a + b) / 2 + r.uniform(-16, 16)
        d = ("M%.1f %.1f Q %.1f %.1f %.1f %.1f"
             % (a, yy, mx, yy + r.uniform(-5, 5), b, yy + r.uniform(-4, 4)))
        out.append("<path d='%s' fill='none' stroke='%s' stroke-width='%.1f' "
                   "stroke-linecap='round' stroke-opacity='%.2f'/>"
                   % (d, color, thick, r.uniform(0.46, 0.64)))
    return "".join(out)


def hellipse(cx, cy, rx, ry, seed):
    """两段不同半径的弧拼成开口椭圆，制造不规则感。"""
    r = _rnd(seed + 77)
    return ("M%.1f %.1f A%.1f %.1f 0 1 1 %.1f %.1f A%.1f %.1f 0 1 1 %.1f %.1f Z"
            % (cx - rx, cy, rx, ry, cx + rx, cy + r.uniform(-4, 4),
               rx + r.uniform(-6, 4), ry + r.uniform(-5, 5), cx - rx, cy))


def arrow(x1, y1, x2, y2, mid, seed=1):
    d = hand_line(x1, y1, x2, y2, seed, seg=8, amp=1.6, over=0)
    return ("<path d='%s' fill='none' stroke='%s' stroke-width='%.1f' "
            "stroke-linecap='round' marker-end='url(#%s)'/>" % (d, INK, SW_ARROW, mid))


def v_arrow(x, y1, y2, mid, seed=3):
    return arrow(x, y1, x, y2, mid, seed)


def defs(mid):
    return ("<defs><marker id='%s' viewBox='0 0 10 10' refX='7.5' refY='5' markerWidth='5' "
            "markerHeight='5' orient='auto-start-reverse'><path d='M2 1L8 5L2 9' fill='none' "
            "stroke='%s' stroke-width='3.1' stroke-linecap='round' stroke-linejoin='round'/>"
            "</marker></defs>" % (mid, INK))


def frame_overlay(kind, seed):
    """整卡外框：pen = 手绘外框 / card = 圆角卡 / none = 无框。"""
    if kind != "pen":
        return ""
    segs = pen_rect(26, 26, W_CARD - 52, H_CARD - 52, seed, amp=2.0, over=(2.0, 7.0))
    return ("<svg class='frame' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s</svg>"
            % (W_CARD, H_CARD, W_CARD, H_CARD, pen_path(segs)))


# ---------------------------------------------------------------- 文本度量
def tw(s, size):
    """估算渲染宽度：CJK 按 1em，其余按 0.62em，再乘实测校准因子。

    校准因子由 pipeline 的 measure 节点回写（真实宽 / 估算宽），
    所以 fit() 的缩字号决策会越跑越准——这是反馈闭环的一半，
    另一半是 measure 对真实溢出的检测。
    """
    return sum(size * (1.0 if ord(c) > 0x2E80 else 0.62) for c in s) * CALIB[0]


def fit(s, size, maxw, tag=""):
    """字号自适应：超出可用宽度就等比缩，缩过头会记 warning 供作者精简文案。"""
    w = tw(s, size)
    if w <= maxw:
        return size
    ns = int(size * maxw / w)
    if ns < 28:
        WARN.append("[%s] 缩到 %dpx（原 %dpx）｜%s" % (tag, ns, size, s[:34]))
    return max(20, ns)


def txt(x, y, s, size=SIZES["body"], anchor="middle", fill=C_TEXT,
        maxw=None, tag="", family=None, weight=None, textlength=None):
    if maxw:
        size = fit(s, size, maxw, tag)
    a = ""
    if family:
        a += " font-family='%s'" % family
    if weight:
        a += " font-weight='%s'" % weight
    if textlength:
        # 字体度量估不准时，直接用 SVG 的 textLength 强制占满指定宽度。
        # lengthAdjust=spacingAndGlyphs 会等比压缩字距和字形，绝不出界。
        a += " textLength='%.1f' lengthAdjust='spacingAndGlyphs'" % textlength
    return ("<text x='%s' y='%s' text-anchor='%s' font-size='%s' fill='%s'%s "
            "letter-spacing='-1.6'>%s</text>"
            % (x, y, anchor, size, fill, a, esc(s.replace(" ", "\u00a0"))))


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def wrap_text(s, size, maxw):
    """按可用宽度断行。优先在中文标点/空格处断，断点太靠前才硬断。"""
    lines, cur = [], ""
    for ch in s:
        if cur and tw(cur + ch, size) > maxw:
            cut = -1
            for p in "，。；：、,.;:）) ／/":
                cut = max(cut, cur.rfind(p))
            if cut >= len(cur) * 0.45:
                lines.append(cur[:cut + 1])
                cur = cur[cut + 1:]
            else:
                lines.append(cur)
                cur = ""
        cur += ch
    if cur:
        lines.append(cur)
    return lines


def txt_block(cx, y, s, size=SIZES["note"], maxw=None, fill=C_NOTE,
              line_h=None, max_lines=None, tag="", align="center"):
    """居中多行文本。超出 max_lines 时最后一行补省略号，绝不让字号缩到看不清。"""
    if not s:
        return ""
    maxw = maxw or W_INNER
    lines = wrap_text(s, size, maxw)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
    line_h = line_h or size * 1.34
    out = []
    y0 = y - (len(lines) - 1) * line_h * 0.5
    for i, ln in enumerate(lines):
        out.append(txt(cx, y0 + i * line_h, ln, size, fill=fill, tag=tag,
                       anchor="start" if align == "start" else "middle"))
    return "".join(out)


# ---------------------------------------------------------------- 高亮语法
# 规格里的文字支持 [[关键词]] 或 [[关键词|b]] 表示加蜡笔底色，b=blue y=yellow p=pink g=gray
HL_RE = re.compile(r"\[\[(.+?)(?:\|([a-z]{1,2}))?\]\]")
COLOR_KEY = {"y": "yellow", "b": "blue", "p": "pink", "g": "gray",
             "gr": "green", "o": "orange"}


class Palette:
    """颜色轮换器。

    用户反馈：整页全黄太单调。方框填色和蜡笔色带都从这里按顺序取，
    一页之内蓝→黄→粉→灰轮着来；跨卡用不同起点，卡与卡之间也不同。
    规格里显式指定的颜色（fill / [[x|b]]）永远优先，且不消耗轮换。
    """

    ORDER = ["blue", "yellow", "pink", "green", "gray", "orange"]

    def __init__(self, start=0):
        self.i = start % len(self.ORDER)

    def next(self):
        c = PAL[self.ORDER[self.i % len(self.ORDER)]]
        self.i += 1
        return c


def parse_hl(text, palette=None, plain=False):
    """把 '① 注入 [[tools 定义]]' 解析成 [(片段, 底色或 None), ...]。

    显式指定的颜色（[[x|b]]）优先；没指定时从 palette 轮换取色，
    没有 palette 才回退到固定黄色。
    """
    if plain:
        return [(strip_hl(text), None)]
    parts, pos = [], 0
    for m in HL_RE.finditer(text):
        if m.start() > pos:
            parts.append((text[pos:m.start()], None))
        key = m.group(2)
        if key and key in COLOR_KEY:
            col = PAL[COLOR_KEY[key]]
        elif palette is not None:
            col = palette.next()
        else:
            col = PAL["yellow"]
        parts.append((m.group(1), col))
        pos = m.end()
    if pos < len(text):
        parts.append((text[pos:], None))
    return parts or [(text, None)]


def strip_hl(text):
    return HL_RE.sub(lambda m: m.group(1), text)


def hl_line(cx, y, parts, size=SIZES["body"], seed=1, pad=8, align="center",
            maxw=None):
    """一行居中文本，可给任意片段涂蜡笔底色。

    ★ 必须「先画完所有色带、再统一画所有文字」——逐段交替输出时，
      后一段的色带会盖住前一段的文字。
    """
    total = sum(tw(t, size) for t, _ in parts) * 1.06   # 实际渲染宽估计
    if maxw and total > maxw:
        size = max(20, int(size * maxw / total))
        total = sum(tw(t, size) for t, _ in parts) * 1.06
    x = cx - total / 2.0 if align == "center" else cx
    bands, texts = [], []
    for i, (t, col) in enumerate(parts):
        w = tw(t, size)
        if col:
            # tw() 对拉丁偏低、对中文准确 → 按拉丁占比轻微补偿，不做整体放大
            latin = sum(1 for c in t if ord(c) <= 0x2E80)
            f = 1.0 + 0.08 * (latin / float(max(1, len(t))))
            bands.append(crayon(x + w / 2.0, y - size * 0.26, w * f + pad * 2,
                                size * 1.02, seed + i * 17, col))
        texts.append(txt(x, y, t, size, anchor="start"))
        x += w
    return "".join(bands) + "".join(texts)


# ---------------------------------------------------------------- 版式
def h1_html(title):
    """主标题：超宽就缩字号，**绝不折行**。

    折行的代价很大——只要多出一行，行尾常常只剩一两个字，非常难看；
    而且会顶掉下方版式的空间。
    """
    size = SIZES["h1"]
    # 有显式换行时按「最长的一行」算，不然两行标题会被无谓缩小
    widest = max(title.split("\n"), key=lambda t: tw(t, size)) if "\n" in title else title
    est = tw(widest, size) * 1.06
    if est > W_INNER:
        size = max(54, int(size * W_INNER / est))
    style = "" if size == SIZES["h1"] else " style='font-size:%dpx'" % size
    body = esc(title).replace("\n", "<br>")
    return "<h1%s>%s</h1>" % (style, body)


def _sub(sub):
    """副标题（HTML 侧）：[[关键词]] → 带蜡笔底色的 span。

    超宽自动缩字号（和 h1 同理：宁可小一号，不要行尾单字成行）。
    """
    if not sub:
        return ""
    size = SIZES["sub"]
    est = tw(strip_hl(sub), size) * 1.06
    style = ""
    if est > W_INNER:
        style = " style='font-size:%dpx'" % max(28, int(size * W_INNER / est))
    return "<div class='sub'%s>%s</div>" % (style, _inline(sub))


def header_height(card):
    """页头（标题 + 副标题 + stage 间距）占掉多少高度——HTML 版式算预算要用。

    踩过的坑：bullets 原来写死 `avail_rows = 960`，但真实可用高度会随标题行数变化
    （标题多一行就少 ~100px），于是 5 条的两行标题页会超出 12px 被门拦下。
    这里按渲染时的同一套几何推导，和 CSS 保持同源。
    """
    title = card.get("title", "") or ""
    lines = title.count("\n") + 1
    size = SIZES["h1"]
    est = tw(title.replace("\n", ""), size) * 1.06
    if est > W_INNER:
        size = max(54, int(size * W_INNER / est))
        if lines == 1 and " " in title:
            lines = 2                      # 中文按字符断行，英文按空格断
    h = size * 1.14 * lines
    sub = card.get("subtitle", "") or ""
    if sub:
        h += 24 + SIZES["sub"] * 1.25
    h += 44                                # .stage 的 margin-top
    h += 12                                # 内容区自身的 margin
    return h


# ---------------------------------------------------------------- 微缩版式
# 供「汇总封面」的四宫格使用：每个格子是一个缩小版版式。
# 全部按「给定矩形 (x, y, w, h) 内画完」的契约实现，不越界。

def _mini_fs(texts, maxw, cap):
    """微缩格子的字号：取能放下**最长单词**的字号，避免英文从中间折断。

    窄格子（约 130px 宽）里 "Observation" 这种词本来就放不下——所以
    微缩格子**优先用中文短词**（参考图也是这么做的）。这里只是尽量兜住。
    """
    longest = 0.0
    for t in texts:
        for w in strip_hl(str(t)).split():
            longest = max(longest, tw(w, 100) / 100.0)
    if not longest:
        return cap
    return int(max(15, min(cap, maxw / (longest * 1.06))))


def _mini_list(x, y, w, h, items, pal, seed, q):
    """微缩清单：每行一个勾 + 文字（行可上色）。"""
    n = max(1, len(items))
    g = 12
    rh = int((h - (n - 1) * g) / n)
    out = []
    fs = int(q.get("fs") or min(36, max(24, rh * 0.34)))
    for i, it in enumerate(items):
        y0 = y + i * (rh + g)
        fill = PAL.get(it.get("fill")) or pal.next()
        out.append(pen_box(x, y0, w, rh, seed + i * 7, fill))
        cy = y0 + rh / 2
        out.append("<path d='M%.1f %.1f l%.1f %.1f l%.1f %.1f' fill='none' stroke='%s' "
                   "stroke-width='4.5' stroke-linecap='round' stroke-linejoin='round'/>"
                   % (x + 22, cy, 10, 10, 12, -19, INK))
        out.append(hl_line(x + 50 + (w - 50) / 2, cy + fs * 0.34,
                           parse_hl(it.get("text", ""), pal, plain=True), fs,
                           seed + i, maxw=w - 60))
    return "".join(out)


def _mini_boxes(x, y, w, h, items, pal, seed, q):
    """微缩并列框：N 个方框横排 + 可选底部一行说明。"""
    n = max(1, len(items))
    line = q.get("line")
    g = 12
    bw = int((w - (n - 1) * g) / n)
    bh = int(h * (0.60 if line else 0.90))
    out = []
    fs = int(q.get("fs") or _mini_fs([i.get("text", "") for i in items],
                                     bw - 16, min(34, max(22, bw * 0.20))))
    for i, it in enumerate(items):
        x0 = x + i * (bw + g)
        fill = PAL.get(it.get("fill")) or pal.next()
        out.append(pen_box(x0, y, bw, bh, seed + i * 9, fill))
        out.append(txt_block(x0 + bw / 2, y + bh / 2 + fs * 0.2,
                             strip_hl(it.get("text", "")), fs, bw - 16,
                             max_lines=2, tag="mb-t%d" % i))
        if it.get("desc"):
            out.append(txt_block(x0 + bw / 2, y + bh - 34, strip_hl(it["desc"]),
                                 24, bw - 16, max_lines=1, tag="mb-d%d" % i))
    if line:
        y1 = y + bh + 14
        h1 = h - bh - 14
        out.append(pen_box(x, y1, w, h1, seed + 77, BOX))
        out.append(hl_line(x + w / 2, y1 + h1 / 2 + 11,
                           parse_hl(line, pal), int(q.get("fs2") or 30),
                           seed + 3, maxw=w - 30))
    return "".join(out)


def _mini_nested(x, y, w, h, items, pal, seed, q):
    """微缩嵌套：一个大框内嵌 N 个子框，底部可选一排 chip。"""
    out = [pen_box(x, y, w, h, seed, BOX)]
    n = max(1, len(items))
    g = 12
    iw = int((w - 32 - (n - 1) * g) / n)
    ih = int((h - 120) if q.get("chips") else (h - 40))
    fs = int(q.get("fs") or _mini_fs([i.get("text", "") for i in items],
                                     iw - 16, min(34, max(22, iw * 0.22))))
    for i, it in enumerate(items):
        x0 = x + 16 + i * (iw + g)
        fill = PAL.get(it.get("fill")) or pal.next()
        out.append(pen_box(x0, y + 18, iw, ih, seed + i * 11, fill))
        out.append(txt_block(x0 + iw / 2, y + 18 + fs * 1.2,
                             strip_hl(it.get("text", "")), fs, iw - 16,
                             max_lines=2, tag="mn-t%d" % i))
        if it.get("desc"):
            out.append(txt_block(x0 + iw / 2, y + 18 + fs * 1.2 + 56,
                                 strip_hl(it["desc"]), 24, iw - 18, max_lines=2,
                                 tag="mn-d%d" % i))
    chips = q.get("chips") or []
    if chips:
        cw = int((w - 32 - (len(chips) - 1) * 12) / len(chips))
        for i, c in enumerate(chips):
            x0 = x + 16 + i * (cw + 12)
            out.append(pen_box(x0, y + h - 88, cw, 68, seed + i * 13, pal.next()))
            out.append(hl_line(x0 + cw / 2, y + h - 45,
                               parse_hl(c, pal, plain=True), 28, seed + i,
                               maxw=cw - 14))
    return "".join(out)


def _mini_steps(x, y, w, h, items, pal, seed, q):
    """微缩步骤：N 个块横排 + 箭头。"""
    n = max(1, len(items))
    g = 24
    bw = int((w - (n - 1) * g) / n)
    bh = int(h * 0.52)
    yy = y + (h - bh) / 2
    fs = int(q.get("fs") or _mini_fs([i.get("text", "") for i in items],
                                     bw - 16, min(30, max(20, bw * 0.20))))
    out = []
    for i, it in enumerate(items):
        x0 = x + i * (bw + g)
        fill = PAL.get(it.get("fill")) or pal.next()
        out.append(pen_box(x0, yy, bw, bh, seed + i * 15, fill))
        out.append(txt_block(x0 + bw / 2, yy + bh / 2 + fs * 0.2,
                             strip_hl(it.get("text", "")), fs, bw - 16,
                             max_lines=2, tag="ms-t%d" % i))
        if i < n - 1:
            out.append(arrow(x0 + bw, yy + bh / 2, x0 + bw + g, yy + bh / 2,
                             "a0", seed + i))
    if q.get("line"):
        out.append(hl_line(x + w / 2, y + h - 18, parse_hl(q["line"], pal),
                           28, seed + 5, maxw=w - 20))
    return "".join(out)


MINI = {"list": _mini_list, "boxes": _mini_boxes,
        "nested": _mini_nested, "steps": _mini_steps}


def layout_hub(card, seed):
    """中心圆 + 并列概念框（原封面版式，现为独立版式，任何页都能用）。"""
    items = card.get("items", [])
    n = len(items)
    pal = Palette(seed)
    avail = 940
    bx = BOX_INSET
    bw = W_INNER - 2 * bx
    parts = [defs("a0")]
    if n <= 3:
        gap = 40
        w = (bw - gap * (n - 1)) // max(1, n)
        top, bh, cy = 430, 300, 200
        parts.append("<path d='%s' fill='%s' stroke='%s' stroke-width='%.1f'/>"
                     % (hellipse(W_INNER / 2, cy, 124, 108, 1), BOX, INK, SW_LINE))
        if card.get("hub"):
            parts.append(txt(W_INNER / 2, cy + 19, card["hub"], 54, maxw=200,
                             tag="hub-title"))
        for i, it in enumerate(items):
            x = bx + i * (w + gap)
            fill = it.get("color") and PAL.get(it["color"]) or pal.next()
            parts.append(pen_box(x, top, w, bh, i * 11 + 3, fill))
            if it.get("big"):
                parts.append(txt(x + w / 2, top + 92, it["big"], 58,
                                 maxw=w - 24, tag="hub-big%d" % i))
            en = str(it.get("en") or "")
            if en and tw(en, 33) > w - 32 and " " in en:
                head, tail = en.split(" ", 1)
                parts.append(txt(x + w / 2, top + 154, head, 33, maxw=w - 32,
                                 tag="hub-en%d" % i))
                parts.append(txt(x + w / 2, top + 196, tail, 33, maxw=w - 32,
                                 tag="hub-en%d-b" % i))
            elif en:
                parts.append(txt(x + w / 2, top + 172, en, 33, maxw=w - 32,
                                 tag="hub-en%d" % i))
            if it.get("tag"):
                parts.append(txt(x + w / 2, top + 248, it["tag"], 46))
            parts.append(arrow(W_INNER / 2, cy + 110, x + w / 2, top - 6, "a0", i * 7 + 5))
    else:
        bh, gap = 132, 30
        top = 40
        for i, it in enumerate(items):
            y = top + i * (bh + gap)
            parts.append(pen_box(bx, y, bw, bh, i * 11 + 3, pal.next()))
            parts.append(hl_line(W_INNER / 2, y + 82,
                                 parse_hl(it.get("text", it.get("big", "")), pal,
                                          plain=True),
                                 SIZES["body"], i * 13 + 5))
    if card.get("note"):
        parts.append(txt_block(W_INNER / 2, avail - 66, strip_hl(card["note"]),
                               SIZES["note"], W_INNER, max_lines=2, tag="hub-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def layout_cover(card, seed):
    """汇总封面：文档标题由页头统一渲染，下面是 **2×2 四宫格**，
    每格一个「微缩版式」（自己带小标题标签）。

    设计意图：读者拿到一套图，最先想知道"这套图讲了什么"。四宫格把四个要点
    各用一个缩小版版式铺出来，等于把目录做成了封面。

    规格：
      quads: [ {label, mini, items[], ...} ]  ≤4 个（不足则留空）
        mini = list  微缩清单（每行一个勾）
             | boxes 微缩并列框（可带 line 底部说明）
             | nested 微缩嵌套（大框内嵌小框，可带 chips）
             | steps 微缩步骤（横排块 + 箭头）
    """
    quads = (card.get("quads") or [])[:4]
    if not quads and card.get("items"):
        # 向后兼容：老规格用 items 表达封面 → 自动按 hub（中心圆）渲染
        WARN.append("[cover] 没写 quads，已按老式封面（中心圆）渲染；"
                    "四宫格新写法见 docs/layouts.md")
        return layout_hub(card, seed)
    pal = Palette(seed)
    bx = BOX_INSET
    bw = W_INNER - 2 * bx
    g = 22
    note_h = 54 if card.get("note") else 0
    avail = 944 - (54 if not card.get("note") else 0)   # 实测可用高度
    tw_ = (bw - g) // 2
    th_ = (avail - note_h - g) // 2
    parts = [defs("a0")]
    for i, q in enumerate(quads):
        x = bx + (i % 2) * (tw_ + g)
        y = (i // 2) * (th_ + g)
        parts.append(pen_box(x, y, tw_, th_, i * 17 + 5, BOX))
        if q.get("label"):
            # 没写 [[高亮]] 也给它一条底色 —— 参考图里每个模块标签都有彩色小标签
            lb = parse_hl(q["label"], pal)
            if all(c is None for _, c in lb):
                lb = [(strip_hl(q["label"]), pal.next())]
            parts.append(hl_line(x + tw_ / 2, y + 50, lb, 34, i * 9 + 3,
                                 maxw=tw_ - 44))
        fn = MINI.get(q.get("mini") or "list")
        if fn is None:
            WARN.append("[cover-quad%d] 未知 mini 类型 %r（可用：%s）"
                        % (i + 1, q.get("mini"), "/".join(MINI)))
            continue
        parts.append(fn(x + 22, y + 84, tw_ - 44, th_ - 108,
                        q.get("items") or [], pal, i * 23 + 7, q))
    if card.get("note"):
        parts.append(txt_block(W_INNER / 2, avail + note_h - 24, strip_hl(card["note"]),
                               SIZES["note"], W_INNER, max_lines=1, tag="cover-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail + note_h, W_INNER, avail + note_h, "".join(parts)))


def layout_chain(card, seed):
    """竖向步骤链：每个方框都上色，颜色按页轮换。"""
    steps = card.get("steps", [])
    pal = Palette(seed)
    n = max(1, len(steps))
    avail = 900
    note = card.get("note")
    band = avail - (76 if note else 0)
    bh = min(150, int((band - (n - 1) * 34) / n))
    step = bh + 34
    top = (band - (n * bh + (n - 1) * 34)) / 2.0
    bx = BOX_INSET
    bw = W_INNER - 2 * bx
    parts = [defs("a0")]
    if card.get("dashed"):
        dy0 = top - 44
        dh = n * bh + (n - 1) * 34 + 76
        parts.append(dash_box(bx - 8, dy0, bw + 16, dh, seed + 99,
                               card.get("dashed_label")))
    for i, st in enumerate(steps):
        y = top + i * step
        f = st.get("fill")
        fill = PAL.get(f) if f else pal.next()
        parts.append(pen_box(bx, y, bw, bh, i * 7 + 3, fill))
        parts.append(hl_line(W_INNER / 2, y + bh / 2 + 17,
                             parse_hl(st.get("text", ""), pal, plain=bool(fill)),
                             SIZES["body"], i * 11 + 3, maxw=bw - 24))
        if i < n - 1:
            parts.append(v_arrow(W_INNER / 2, y + bh, y + step - 2, "a0", i * 13 + 3))
    if note:
        parts.append(txt_block(W_INNER / 2, avail - 34, strip_hl(note),
                               SIZES["note"], W_INNER, max_lines=2, tag="chain-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def layout_cycle(card, seed):
    """环形循环：N 个节点围一圈，弧形箭头顺时针连（ReAct / PDCA 这类）。

    弧线用 SVG 的 A（椭圆弧）命令沿圆走，不用 Q 控制点——
    Q 的控制点算错就会让弧线穿过圆心。
    顶部关键词链：只在放不下时才压缩（textLength），
    短词（如「答案」）用自然宽度，否则色带会变成一块扁平色块。
    """
    nodes = card.get("nodes", [])
    pal = Palette(seed)
    n = max(3, min(6, len(nodes)))
    avail = 900
    parts = [defs("a0")]
    cx, cy = W_INNER / 2.0, 512
    R = 232
    bw, bh = 214, 92
    kws = card.get("keywords") or []
    slot = (W_INNER - 40) / float(max(1, len(kws))) if kws else 0
    # 统一字号：取「能装下最长那个词」的字号，四个词一样大。
    # 早先按槽位 textLength 压缩，长词被压小、短词显大，用户指出"字体应该统一"。
    ksize = 40
    if kws:
        max_em = max(tw(k, 100) / 100.0 for k in kws)
        ksize = min(40, int(slot * 0.98 / (max_em * 1.08)))
    for i, k in enumerate(kws):
        est = tw(k, ksize) * 1.08
        x0 = 20 + i * slot
        col = pal.next()
        parts.append(crayon(x0 + slot / 2, 92 - ksize * 0.26, est + 14, ksize * 1.02,
                            seed + i * 17, col))
        parts.append(txt(x0 + slot / 2, 92, k, ksize))
    ang0 = -math.pi / 2
    centers = [(cx + R * math.cos(ang0 + 2 * math.pi * i / n),
                cy + R * math.sin(ang0 + 2 * math.pi * i / n)) for i in range(n)]
    for i, nd in enumerate(nodes[:n]):
        x, y = centers[i]
        fill = PAL.get(nd.get("fill")) or pal.next()
        parts.append(pen_box(x - bw / 2, y - bh / 2, bw, bh, i * 15 + 3, fill))
        parts.append(txt(x, y + 6, strip_hl(nd.get("text", "")), 44, maxw=bw - 24,
                         tag="cycle-%d" % i))
        if nd.get("desc"):
            dy = y - bh / 2 - 40 if i == 0 else y + bh / 2 + 44
            parts.append(txt_block(x, dy, strip_hl(nd["desc"]), 30, 250,
                                   max_lines=2, tag="cycle-d%d" % i))
    r_arc = R * 1.04
    for i in range(n):
        a1 = ang0 + 2 * math.pi * i / n + math.pi / n * 0.62
        a2 = ang0 + 2 * math.pi * ((i + 1) % n) / n - math.pi / n * 0.62
        x1, y1 = cx + r_arc * math.cos(a1), cy + r_arc * math.sin(a1)
        x2, y2 = cx + r_arc * math.cos(a2), cy + r_arc * math.sin(a2)
        parts.append("<path d='M%.1f %.1f A%.1f %.1f 0 0 1 %.1f %.1f' fill='none' "
                     "stroke='%s' stroke-width='%.1f' stroke-linecap='round' "
                     "marker-end='url(#a0)'/>" % (x1, y1, r_arc, r_arc, x2, y2, INK, SW_ARROW))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def layout_spectrum(card, seed):
    """A→B 单步骤详情：一条渐变箭头从 A 指到 B，下面列细节。

    渐变两端**不要用近黑**——用户明确说「箭头开始和结束都是黑色，不对」，
    两端用中灰过渡，中段才是彩色。
    """
    pal = Palette(seed)
    avail = 900
    bx = BOX_INSET
    bw = W_INNER - 2 * bx
    parts = [defs("a0")]
    # 渐变只留 蓝 → 粉：两端不要灰也不要黑（用户明确要求）
    stops = card.get("gradient") or [(PAL["blue"], "0"), (PAL["pink"], "1")]
    parts.append(_poly_fill([(bx - 10, 152), (bx + bw + 10, 152),
                             (bx + bw + 10, 254), (bx - 10, 254)],
                            seed + 5, 2.0, "#FFFFFF"))     # 箭头底色：白
    parts.append(grad_arrow(bx, 168, bw, 70, "specgrad%d" % seed, stops))
    ends = card.get("ends") or []
    if len(ends) == 2:
        parts.append(txt(bx + 6, 288, ends[0], 42, anchor="start", weight="700"))
        parts.append(txt(bx + bw - 6, 288, ends[1], 42, anchor="end", weight="700"))
    if card.get("stages"):
        parts.append(txt(W_INNER / 2, 118, " → ".join(card["stages"]), 36,
                         maxw=bw, tag="spec-stages"))
    items = card.get("items", [])
    n_it = max(1, len(items))
    # 间距自适应：条数少就拉开，别在底部留一大块空白
    step = int(min(150, (avail - 470) / n_it)) if card.get("note") else \
        int(min(150, (avail - 430) / n_it))
    y = 400
    for i, it in enumerate(items):
        parts.append("<circle cx='%.1f' cy='%.1f' r='8' fill='%s'/>"
                     % (bx + 16, y - 16, INK))
        parts.append(hl_line(bx + 44, y, parse_hl(it.get("text", it.get("head", "")), pal),
                             48, seed + i * 13 + 5, align="start", maxw=bw - 100))
        y += 112
    if card.get("note"):
        parts.append(txt_block(W_INNER / 2, y + 30, strip_hl(card["note"]),
                               SIZES["note"], W_INNER, max_lines=1, tag="spec-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def layout_timeline(card, seed):
    """纵向时间轴：**竖轴水平居中**，节点文字左右轮流分布（两侧各一遍）。

    全靠右的摆法在节点少时右侧全是字、左侧全空；居中轴 + 左右交替
    视觉平衡最好，也是时间轴最经典的画法。
    """
    steps = card.get("steps", [])
    pal = Palette(seed)
    n = max(2, min(6, len(steps)))
    avail = 900
    ax = W_INNER / 2.0                 # 竖轴水平居中
    top, bottom = 78, 770
    col_w = 330                        # 左右两列文字块宽度
    parts = [defs("a0")]
    parts.append("<path d='%s' fill='none' stroke='%s' stroke-width='%.1f' "
                 "stroke-linecap='round'/>"
                 % (hand_line(ax, top - 24, ax, bottom + 24, seed, 12, 1.5, 3),
                    INK, SW_LINE * 0.8))
    step = (bottom - top) / max(1, n - 1)
    for i, st in enumerate(steps[:n]):
        y = top + i * step
        fill = PAL.get(st.get("fill")) or pal.next()
        parts.append("<circle cx='%.1f' cy='%.1f' r='15' fill='%s'/>" % (ax, y, fill))
        left = (i % 2 == 0)
        cx = ax - 48 - col_w / 2.0 if left else ax + 48 + col_w / 2.0
        x1 = ax - 15 if left else ax + 15
        x2 = ax - 48 if left else ax + 48
        parts.append(hand_line(x1, y, x2, y, seed + i, 3, 1.2, 2))
        parts.append(hl_line(cx, y - 10, parse_hl(st.get("text", ""), pal, plain=True),
                             42, seed + i * 9, maxw=col_w))
        if st.get("desc"):
            parts.append(txt_block(cx, y + 36, strip_hl(st["desc"]), 30, col_w,
                                   max_lines=2, tag="tl-d%d" % i))
    if card.get("note"):
        parts.append(txt_block(W_INNER / 2, avail - 20, strip_hl(card["note"]),
                               SIZES["note"], W_INNER, max_lines=1, tag="tl-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def layout_flow(card, seed):
    """横向节点链：节点带说明，底部不再留大片空白。"""
    nodes = card.get("nodes", [])
    pal = Palette(seed)
    n = max(1, len(nodes))
    avail = 900
    bx = BOX_INSET
    bw = W_INNER - 2 * bx
    gap = 26
    w = (bw - gap * (n - 1)) // n
    bh = 176
    top = 170
    parts = [defs("a0")]
    if card.get("dashed"):
        parts.append(dash_box(bx - 8, top - 56, bw + 16, bh + 84, seed + 99,
                              card.get("dashed_label")))
    for i, nd in enumerate(nodes):
        x = bx + i * (w + gap)
        fill = PAL.get(nd.get("fill")) or pal.next()
        parts.append(pen_box(x, top, w, bh, i * 15 + 3, fill))
        parts.append(hl_line(x + w / 2, top + 62,
                             parse_hl(nd.get("text", ""), pal, plain=bool(fill)),
                             SIZES["body"] - 10, pad=6, align="center", maxw=w - 24))
        if nd.get("desc"):
            parts.append(txt_block(x + w / 2, top + 118, strip_hl(nd["desc"]), 26,
                                   w - 26, max_lines=2, tag="flow-d%d" % i,
                                   align="center"))
        if i < n - 1:
            parts.append(arrow(x + w, top + bh / 2, x + w + gap, top + bh / 2,
                               "a0", i * 19 + 2))
    y = top + bh + 108
    if card.get("mid"):
        parts.append(txt(W_INNER / 2, 104, strip_hl(card["mid"]), SIZES["note"] + 2,
                         fill=C_NOTE, maxw=W_INNER))
    if card.get("note"):
        parts.append(txt_block(W_INNER / 2, y, strip_hl(card["note"]),
                               SIZES["body"] - 6, W_INNER, max_lines=2, tag="flow-note"))
        y += 58
    if card.get("note2"):
        parts.append(txt_block(W_INNER / 2, y, strip_hl(card["note2"]),
                               SIZES["note"], W_INNER, max_lines=2, tag="flow-note2"))
    bottom = card.get("bottom") or []
    if bottom:
        m = len(bottom)
        cwid = (bw - (m - 1) * 24) // m
        for i, c in enumerate(bottom):
            x = bx + i * (cwid + 24)
            parts.append(pen_box(x, 700, cwid, 150, i * 23 + 5,
                                 PAL.get(c.get("fill")) or pal.next()))
            parts.append(txt(x + cwid / 2, 758, strip_hl(c.get("text", "")), 36,
                             maxw=cwid - 24, tag="flow-b%d" % i))
            if c.get("desc"):
                parts.append(txt_block(x + cwid / 2, 806, strip_hl(c["desc"]), 26,
                                       cwid - 26, max_lines=2, tag="flow-bd%d" % i,
                                       align="center"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def layout_bullets(card, seed):
    """清单：行**高度由浏览器分配**（.bullets 是 flex 列，行 flex:1 1 0），
    ink 只按条数缩放字号，不做任何高度算术。

    三次踩坑记：
      1. 给行设 min-height 下限 → 条数多时下限反而把卡片撑破；
      2. 压 min-height 没用——行高实际由内容（padding+head+desc ≈178px）决定；
      3. 自己推导"可用高度"也靠不住——带 [[高亮]] 的副标题会让行盒高出约 60px，
         算不准。正解是**别算**：卡片是 flex 列，.bullets 吃掉剩余空间，
         每行 flex:1 1 0 均分，浏览器保证永不溢出（gate 仍作为兜底）。
    """
    items = card.get("items", [])
    pal = Palette(seed)
    n = max(1, len(items))
    # 只决定字号：条数越多字越小（可读性下限 24px）
    unit = min(1.0, 4.6 / n)
    head_fs = max(24, int(48 * unit))
    desc_fs = max(22, int(38 * unit))
    rows = []
    for it in items:
        fill = PAL.get(it.get("fill")) or pal.next()
        plain = bool(fill)      # 行已上色，行内不再画色带
        head = _inline(it.get("head", "")) if not plain else esc(strip_hl(it.get("head", "")))
        desc = _inline(it.get("desc", "")) if not plain else esc(strip_hl(it.get("desc", "")))
        no = "<span class='no'>%s</span>" % esc(it["no"]) if it.get("no") else ""
        rows.append(
            "<div class='row' style='background:%s;'>"
            "<div class='head' style='font-size:%dpx'>%s%s</div>"
            "%s</div>"
            % (fill, head_fs, no, head,
               ("<div class='desc' style='font-size:%dpx;margin-top:%dpx'>%s</div>"
                % (desc_fs, max(4, int(12 * unit)), desc)) if desc else ""))
    return "<div class='bullets'>%s</div>" % "".join(rows)


def _inline(text):
    """HTML 内联高亮（显式指定的颜色才生效）。"""
    if not text:
        return ""
    out, pos = [], 0
    for m in HL_RE.finditer(text):
        out.append(esc(text[pos:m.start()]))
        col = COLOR_KEY.get(m.group(2) or "", "y")
        out.append("<span class='hl %s'>%s</span>" % (col, esc(m.group(1))))
        pos = m.end()
    # 尾巴必须补上：否则「[[高亮]]后面的文字」会被静默吃掉，
    # 完全没有 [[高亮]] 的副标题更是整条变空（和 parse_hl 保持同一套语义）
    if pos < len(text):
        out.append(esc(text[pos:]))
    return "".join(out)


def layout_compare(card, seed):
    """左右两列对照：内层子框自适应高度填满外框，颜色轮换。"""
    left, right = card.get("left", {}), card.get("right", {})
    pal = Palette(seed)
    col_w, gap = 384, 40
    avail = 950
    parts = [defs("a0")]
    box_y, box_h, pad = 90, 760, 36

    def col(cfg, x0, seed0):
        g = [hl_line(x0 + col_w / 2, 52, parse_hl(cfg.get("label", ""), pal),
                     44, seed0, maxw=col_w - 20)]
        g.append(pen_box(x0 + 3, box_y, col_w - 6, box_h, seed0 + 1, None))
        blocks = cfg.get("blocks", [])
        n = max(1, len(blocks))
        area_y = box_y + pad
        area_h = box_h - 2 * pad
        bh = (area_h - (n - 1) * 22) / float(n)
        for i, b in enumerate(blocks):
            f = b.get("fill") if isinstance(b, dict) else None
            fill = PAL.get(f) if f else pal.next()
            text = b.get("text", "") if isinstance(b, dict) else b
            y = area_y + i * (bh + 22)
            g.append(pen_box(x0 + 30, y, col_w - 60, bh, seed0 + i * 13 + 9, fill))
            g.append(hl_line(x0 + col_w / 2, y + bh / 2 + 12,
                             parse_hl(text, pal, plain=not (f in (None, "none"))), 34,
                             pad=6, maxw=col_w - 72))
        if cfg.get("note"):
            g.append(txt_block(x0 + col_w / 2, box_y + box_h + 56,
                               strip_hl(cfg["note"]), 34, col_w - 12, max_lines=2,
                               tag="cmp-note"))
        return "".join(g)

    parts.append(col(left, BOX_INSET, 5))
    parts.append(col(right, BOX_INSET + col_w + gap, 15))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def layout_arch(card, seed):
    """结构图：大框内嵌子框 → 箭头 → 一个框，底部一排 chip。"""
    pal = Palette(seed)
    bx = BOX_INSET
    parts = [defs("a0")]
    hw = 446
    parts.append(pen_box(bx, 16, hw, 380, 3, PAL.get(card.get("host_fill"))))
    if card.get("host_label"):
        parts.append(hl_line(bx + hw / 2, 74, parse_hl(card["host_label"], pal), 42, 21, maxw=hw - 30))
    for i, sub in enumerate(card.get("inner", [])):
        x = bx + 26 + i * 210
        parts.append(pen_box(x, 168, 190, 190, i * 10 + 13,
                             PAL.get(sub.get("fill")) or pal.next()))
        parts.append(txt(x + 95, 232, strip_hl(sub.get("text", "")), 44))
        if sub.get("desc"):
            parts.append(txt(x + 95, 296, strip_hl(sub["desc"]), 24, fill=C_TEXT,
                             maxw=176, tag="arch-in%d" % i))
    ax0 = bx + hw + 6
    parts.append("<path d='%s' fill='none' stroke='%s' stroke-width='%.1f' "
                 "stroke-dasharray='14 10' marker-end='url(#a0)' marker-start='url(#a0)'/>"
                 % (hand_line(ax0, 200, ax0 + 108, 200, 41, 5, 1.8, 0), INK, SW_ARROW))
    if card.get("link_label"):
        parts.append(txt(ax0 + 54, 172, card["link_label"], 26, fill=C_TEXT))
    sw = 246
    sx = W_INNER - bx - sw
    if card.get("server"):
        parts.append(pen_box(sx, 130, sw, 200, 33, PAL.get(card.get("server_fill"))
                             or pal.next()))
        parts.append(txt(sx + sw / 2, 208, strip_hl(card["server"]), 48))
        if card.get("server_desc"):
            parts.append(txt(sx + sw / 2, 268, strip_hl(card["server_desc"]),
                             SIZES["note"] - 8, fill=C_TEXT, maxw=sw - 30,
                             tag="arch-srv"))
    if card.get("line"):
        parts.append(hl_line(W_INNER / 2, 470, parse_hl(card["line"], pal), 44, 31, maxw=W_INNER - 40))
    chips = card.get("chips", [])
    if chips:
        n = len(chips)
        w = (W_INNER - 2 * bx - (n - 1) * 30) // n
        for i, c in enumerate(chips):
            x = bx + i * (w + 30)
            parts.append(pen_box(x, 560, w, 170, i * 11 + 7,
                                 PAL.get(c.get("fill")) or pal.next()))
            parts.append(txt(x + w / 2, 636, strip_hl(c.get("text", "")), 44))
            if c.get("desc"):
                parts.append(txt(x + w / 2, 692, strip_hl(c["desc"]), 30, fill=C_TEXT,
                                 maxw=w - 30, tag="chip%d" % i))
    if card.get("note"):
        parts.append(txt(W_INNER / 2, 820, strip_hl(card["note"]), SIZES["note"] - 6,
                         fill=C_NOTE))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, 900, W_INNER, 900, "".join(parts)))



def layout_matrix(card, seed):
    """2×2 四象限：格子加高铺满，不留大片空白。"""
    cells = card.get("cells", [])
    pal = Palette(seed)
    avail = 900
    bx = BOX_INSET
    bw = W_INNER - 2 * bx
    top, bh = 140, 620
    gap = 26
    cw = (bw - gap) / 2.0
    ch = (bh - gap) / 2.0
    parts = [defs("a0")]
    lab = card.get("labels") or {}
    if lab.get("top"):
        parts.append(txt(bx + bw / 2, 112, strip_hl(lab["top"]), 34, fill=C_NOTE))
    if lab.get("left"):
        parts.append("<text x='%d' y='%d' font-family='Microsoft YaHei' font-size='30' "
                     "fill='%s' transform='rotate(-90 %d %d)'>%s</text>"
                     % (bx - 34, top + bh / 2, C_NOTE, bx - 34, top + bh / 2,
                        esc(lab["left"])))
    for i, c in enumerate(cells[:4]):
        x = bx + (i % 2) * (cw + gap)
        y = top + (i // 2) * (ch + gap)
        fill = PAL.get(c.get("fill")) or pal.next()
        parts.append(pen_box(x, y, cw, ch, i * 17 + 5, fill))
        parts.append(hl_line(x + cw / 2, y + 96,
                             parse_hl(c.get("head", ""), pal, plain=True), 44,
                             seed + i * 9, maxw=cw - 40))
        if c.get("desc"):
            parts.append(txt_block(x + cw / 2, y + 168, strip_hl(c["desc"]),
                                   32, cw - 44, max_lines=4, tag="mx-%d" % i))
    if card.get("note"):
        parts.append(txt_block(W_INNER / 2, avail - 50, strip_hl(card["note"]),
                               SIZES["note"], W_INNER, max_lines=2, tag="mx-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def pen_poly(pts, seed, w=SW_LINE, amp=1.0, over=(1.0, 5.0)):
    """闭合多边形的**手绘描边**：逐边用带笔锋的线段，和方框同一套手感。"""
    segs = []
    n = len(pts)
    for i in range(n):
        ax, ay = pts[i]
        bx_, by_ = pts[(i + 1) % n]
        segs += pen_edge(ax, ay, bx_, by_, seed * 31 + i, w=w, amp=amp, over=over)
    return segs


def _poly_fill(pts, seed, amp=1.6, fill=None):
    """闭合多边形的填充路径（手绘抖动）。"""
    r = _rnd(seed + 313)
    j = [(x + r.uniform(-amp, amp), y + r.uniform(-amp, amp)) for x, y in pts]
    d = "M" + " L".join("%.1f %.1f" % q for q in j) + " Z"
    return "<path d='%s' fill='%s'/>" % (d, fill) if fill else ""


def layout_pyramid(card, seed):
    """金字塔：分层结构，从塔尖到基座逐层变宽。

    `levels` 数组顺序 = **从上到下**（第 1 个在塔尖、最窄；最后一个在基座、最宽）。
    每层是一个梯形（顶边比底边窄，层与层之间宽度连续），层内一行主文案 + 可选说明。

    为什么用梯形而不是"宽度递减的方框"：方框堆叠看起来是条形图，
    梯形的斜边才是"金字塔"的视觉信号。
    """
    levels = card.get("levels") or []
    pal = Palette(seed)
    n = max(2, min(6, len(levels)))
    levels = levels[:n]
    bx = BOX_INSET
    bw = W_INNER - 2 * bx
    hw = bw / 2.0
    note = card.get("note")
    avail = 900
    band = avail - (100 if note else 0)   # 给底部备注留够，否则压在基座上
    g = 10
    th = (band - (n - 1) * g) / float(n)
    min_r = 0.36                              # 塔尖宽度占底宽的比例
    top = (band - (n * th + (n - 1) * g)) / 2.0 + 10
    cx = W_INNER / 2.0
    parts = [defs("a0")]
    for i, lv in enumerate(levels):
        y = top + i * (th + g)
        r_t = min_r + (1 - min_r) * i / float(n)
        r_b = min_r + (1 - min_r) * (i + 1) / float(n)
        pts = [(cx - hw * r_t, y), (cx + hw * r_t, y),
               (cx + hw * r_b, y + th), (cx - hw * r_b, y + th)]
        fill = PAL.get(lv.get("fill")) or pal.next()
        parts.append(_poly_fill(pts, i * 19 + 5, 1.6, fill))
        parts.append(pen_path(pen_poly(pts, i * 19 + 5)))
        size = int(card.get("fs") or max(28, min(48, th * 0.40)))
        if lv.get("desc"):
            parts.append(hl_line(cx, y + th * 0.42, parse_hl(lv.get("text", ""), pal,
                                                              plain=True), size,
                                 i * 11 + 3, maxw=2 * hw * r_b - 56))
            parts.append(txt_block(cx, y + th * 0.42 + size * 1.35,
                                   strip_hl(lv["desc"]), max(22, int(size * 0.62)),
                                   2 * hw * r_b - 60, max_lines=2, tag="py-d%d" % i))
        else:
            parts.append(hl_line(cx, y + th / 2 + size * 0.34,
                                 parse_hl(lv.get("text", ""), pal, plain=True), size,
                                 i * 11 + 3, maxw=2 * hw * r_b - 56))
    if note:
        parts.append(txt_block(W_INNER / 2, avail - 26, strip_hl(note),
                               SIZES["note"], W_INNER, max_lines=2, tag="py-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, avail, W_INNER, avail, "".join(parts)))


def layout_raw(card, seed):
    """逃生舱：直接给一段 SVG。给规格表达不了的特殊页面用。"""
    return card.get("svg", "")


def grad_arrow(x, y, w, h, gid, stops):
    """渐变实心箭头（光谱用）：轴 + 三角头。"""
    shaft = h * 0.44
    y0 = y + (h - shaft) / 2.0
    head = h * 0.92
    d = ("M%.1f %.1f L%.1f %.1f L%.1f %.1f L%.1f %.1f L%.1f %.1f L%.1f %.1f L%.1f %.1f Z"
         % (x, y0, x + w - head, y0, x + w - head, y, x + w, y + h / 2,
            x + w - head, y + h, x + w - head, y0 + shaft, x, y0 + shaft))
    return ("<defs><linearGradient id='%s' x1='0' y1='0' x2='1' y2='0'>%s</linearGradient></defs>"
            "<path d='%s' fill='url(#%s)'/>"
            % (gid, "".join("<stop offset='%s' stop-color='%s'/>" % (c, o) for o, c in stops),
               d, gid))


LAYOUTS = {
    "cover": layout_cover,
    "hub": layout_hub,
    "chain": layout_chain,
    "flow": layout_flow,
    "bullets": layout_bullets,
    "compare": layout_compare,
    "arch": layout_arch,
    "cycle": layout_cycle,
    "spectrum": layout_spectrum,
    "timeline": layout_timeline,
    "matrix": layout_matrix,
    "pyramid": layout_pyramid,
    "raw": layout_raw,
}


# ---------------------------------------------------------------- 页面装配
CSS = """
@font-face{font-family:'KuaiLe';src:url('%FONT%') format('truetype');font-display:block;}
*{margin:0;padding:0;box-sizing:border-box;}
body{width:%WPAGE%px;height:%HPAGE%px;margin:0;background:%BG_PAGE%;
     font-family:%FONT_SANS%;}
.card{position:relative;width:%WCARD%px;height:%HCARD%px;margin:%MARGIN%px auto;
      background:%BG_CARD%;padding:%PAD_TOP%px %PAD_X%px %PAD_TOP%px;overflow:hidden;
      display:flex;flex-direction:column;}
.frame{position:absolute;left:0;top:0;pointer-events:none;z-index:9;}
.deco{position:absolute;left:0;top:0;pointer-events:none;z-index:0;}
.card.round{border-radius:28px;box-shadow:0 6px 26px rgba(0,0,0,.07);}
.card.square{border-radius:8px;}
.card.plain{background:%BG_CARD%;}
h1{font-size:%H1%px;line-height:1.14;text-align:center;color:%C_HEAD%;font-weight:800;
   letter-spacing:-1.5px;}
.sub{font-size:%SUB%px;line-height:1.25;text-align:center;color:%C_TEXT%;font-weight:600;
     margin-top:24px;letter-spacing:-1px;}
.stage{margin-top:44px;display:block;flex:0 0 auto;}
.hl{position:relative;display:inline-block;padding:7px 12px;z-index:0;font-weight:700;}
.hl::before{content:'';position:absolute;left:-6px;right:-6px;top:14%;bottom:-4%;z-index:-1;
  border-radius:4px 8px 5px 9px;transform:rotate(-.8deg);
  background-image:
    repeating-linear-gradient(-1.6deg, rgba(255,255,255,0) 0 5px, rgba(110,100,70,.10) 5px 8px),
    repeating-linear-gradient(1.1deg, rgba(255,255,255,0) 0 9px, rgba(255,255,255,.20) 9px 13px);}
.hl.y::before{background-color:%PAL_Y%}
.hl.b::before{background-color:%PAL_B%}
.hl.p::before{background-color:%PAL_P%}
.hl.g::before{background-color:%PAL_G%}
.hl.gr::before{background-color:%PAL_GR%}
.hl.o::before{background-color:%PAL_O%}
.bullets{margin-top:12px;flex:1 1 auto;min-height:0;
     display:flex;flex-direction:column;justify-content:space-between;}
.row{border:5.6px solid %INK%;border-radius:16px 20px 17px 21px;
     padding:28px 40px;min-height:0;flex:1 1 0;
     display:flex;flex-direction:column;justify-content:center;}
.row .head{font-size:%ROW_HEAD%px;line-height:1.35;color:%C_HEAD%;font-weight:700;
     letter-spacing:-1.5px;}
.row .no{margin-right:16px;}
.row .desc{font-size:38px;line-height:1.5;color:%C_TEXT%;margin-top:12px;}
.foot{position:absolute;left:0;right:0;bottom:44px;text-align:center;
      font-family:%FONT_EMOJI%,'KuaiLe',%FONT_SANS%;font-size:30px;color:#9A9A96;}
"""

DECO_VARIANTS = ["gear1", "gear2", "gear2f1", "gear2f2", "star4", "star5", "star5f"]
DECO_SLOTS = [[(952, 64), (958, 692), (58, 1248)],
              [(46, 64), (958, 692), (948, 1248)]]


def _deco_layer(idx):
    from decor import decor
    parts = ["<svg class='deco' width='%d' height='%d' viewBox='0 0 %d %d' "
             "xmlns='http://www.w3.org/2000/svg'>" % (W_CARD, H_CARD, W_CARD, H_CARD)]
    variants = [DECO_VARIANTS[(idx * 1) % 7], DECO_VARIANTS[(idx * 2 + 3) % 7],
                DECO_VARIANTS[(idx * 3 + 5) % 7]]
    slots = DECO_SLOTS[idx % 2]
    for i, (name, (x, y)) in enumerate(zip(variants, slots)):
        size = (30, 34, 38)[i]
        pair = name.startswith("gear2")
        if pair:
            x -= size * 1.05
        lo, hi = 30 + size * 1.05, W_CARD - 32 - (size * 1.25 if pair else size)
        x = max(lo, min(hi, x))
        y = max(24 + size * 1.15, min(H_CARD - 24 - size * 1.15, y))
        parts.append(decor(name, x, y, size, 300 + i * 7 + idx, 0.42 if pair else 0.46))
    parts.append("</svg>")
    return "".join(parts)


def render_card(card, idx, total, meta, font_url):
    """把一张卡的规格渲染成完整 HTML。"""
    layout = card.get("layout", "bullets")
    if layout not in LAYOUTS:
        raise ValueError("unknown layout: %s（可用：%s）" % (layout, ", ".join(LAYOUTS)))
    frames = meta.get("frame") or ["pen"]      # 空列表/None 都回落到默认，别让取模崩
    if isinstance(frames, str):
        frames = [frames]
    kind = card.get("frame") or frames[idx % len(frames)]

    _BOXES.clear()
    body = LAYOUTS[layout](card, idx * 17 + 7)
    manifest = "<!--T2I_BOXES:%s-->" % json.dumps(_BOXES)
    sub = _sub(card.get("subtitle", ""))
    foot = meta.get("footer", "")
    foot_html = "<div class='foot'>%s</div>" % esc(foot) if foot else ""
    cls = {"pen": "square", "card": "round", "none": "plain"}.get(kind, "square")
    # 四宫格封面已经铺满画面，装饰会压到格子边框 → 这一种版式自动不加装饰
    full_bleed = layout == "cover" and card.get("quads")
    deco = _deco_layer(idx) if (meta.get("decor", True) and not full_bleed) else ""

    repl = [("%FONT%", font_url), ("%WPAGE%", str(W_CARD + MARGIN * 2)),
            ("%HPAGE%", str(H_CARD + MARGIN * 2)), ("%WCARD%", str(W_CARD)),
            ("%HCARD%", str(H_CARD)), ("%MARGIN%", str(MARGIN)),
            ("%PAD_TOP%", str(PAD_TOP)), ("%PAD_X%", str(PAD_X)),
            ("%BG_PAGE%", BG_PAGE), ("%BG_CARD%", BG_CARD), ("%INK%", INK),
            ("%C_HEAD%", C_HEAD), ("%C_TEXT%", C_TEXT), ("%FONT_SANS%", FONT_SANS),
            ("%FONT_EMOJI%", FONT_EMOJI), ("%H1%", str(SIZES["h1"])),
            ("%SUB%", str(SIZES["sub"])), ("%ROW_HEAD%", "48"),
            ("%PAL_Y%", PAL["yellow"]), ("%PAL_B%", PAL["blue"]),
            ("%PAL_P%", PAL["pink"]), ("%PAL_G%", PAL["gray"]),
            ("%PAL_GR%", PAL["green"]), ("%PAL_O%", PAL["orange"])]
    css = CSS
    for k, v in repl:
        css = css.replace(k, v)

    return ("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><style>%s</style></head>
<body><div class="card %s">
<!--T2I_BOXES:%s-->
%s
%s
%s
%s
%s
%s
</div></body></html>""" % (css, cls, manifest, frame_overlay(kind, 4200 + idx),
                           deco, h1_html(card.get("title", "")), sub, body,
                           foot_html))
