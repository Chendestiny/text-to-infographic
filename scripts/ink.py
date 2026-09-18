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
C_NOTE = "#4A4A4A"                      # 小字（备注/说明）：加黑，浅灰在手机上看不清

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
# 本卡登记的文字（净文本）。measure 的内容门会核对「规格里写的字是否真的出现在图上」——
# 见 _reg_text 的注释：文字被静默吞掉时，几何检查永远发现不了。
_TEXTS = []
# 每个文字槽的几何登记：设计字号 / 可用宽度 / 允许行数。
# 容量不是拍脑袋的常数 —— 它由 maxw 与字号推出来，所以契约里那 81 个手写上限
# 只能算"建议值"，真实能不能放下由几何说话（capacity.py / 规格门都用这份登记）。
_CAPS = []
_INK = []          # 墨迹包围盒（箭头/外框/方框），供几何布局门做求交
# DOM 文字模式的文字槽：文字交给浏览器排版，引擎只给"框在哪、多大、最多几行"
# （用户架构方向：折行/省略/垂直居中/自适应缩放都是前端的事，不该用 Python 估算）
_SLOTS = []

# ★ DOM 文字总开关：打开后 txt / txt_block / hl_line 不再画 SVG 文字，而是把文字登记成槽，
#   由浏览器排版。这样**所有版式自动迁移**，不需要逐处改调用点。
#   （已迁移的 flow/chain/compare 自己登记槽，不走这里。）
DOM_TEXT = True

# 高亮颜色反查：parse_hl 给出的是 hex，DOM 需要 CSS 类名（y/b/p/g/gr/o）
_NAME_BY_HEX = {}


def _hl_key(hex_or_name):
    """把调色板 hex / 名字换成高亮类名字母（y/b/p/g/gr/o）。"""
    if not hex_or_name:
        return "y"
    if hex_or_name in COLOR_KEY:          # 已经是字母
        return hex_or_name
    for letter, name in COLOR_KEY.items():
        if PAL.get(name) == hex_or_name or name == hex_or_name:
            return letter
    return "y"


def _reg_slot(x, y, w, h, text, size, clamp=2, align="center", min_size=15, weight=None):
    """登记一个 DOM 文字槽：位置 + 尺寸 + 字号 + 行数上限，其余交给浏览器。"""
    _SLOTS.append({"x": float(x), "y": float(y), "w": float(w), "h": float(h),
                   "text": str(text), "size": int(size), "clamp": int(clamp),
                   "align": align, "min": int(min_size), "weight": weight})


# DOM 文字的样式：折行、行数上限（line-clamp）、垂直居中全靠 CSS ；
# 高亮继续用基础 CSS 里已有的 .hl（蜡笔质感 ::before），DOM 模式下不降级
DOM_SLOT_CSS = """
/* ★ 坐标系必须同源：.stage 原本自带 margin-top:44px，而 margin 在元素**外面**，
   覆盖层从 wrapper 的内容盒起算 → DOM 文字整体比 SVG 内容高 44px（实测标签压在方框顶边上）。
   把 margin 移到 wrapper，stage 归零 —— 两个坐标系就重合了。 */
.stagewrap { position: relative; margin-top: 44px; }
.stagewrap > svg.stage { display: block; margin-top: 0; }
.slots { position: absolute; inset: 0; }
.slots .s { position: absolute; display: flex; align-items: center; justify-content: center; }
.slots .s.left { justify-content: flex-start; }
.slots .t {
  /* break-word（不是 anywhere）：整词放不下才断，绝不在词内断 —— 与 Python 侧一致 */
  width: 100%; box-sizing: border-box;   /* 必须填满槽宽：否则 flex 里收缩到内容宽，折行不受控 */
  overflow-wrap: break-word; word-break: normal; line-height: 1.26; text-align: center;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: var(--clamp, 2);
  overflow: hidden; color: %C_TEXT%; font-family: %FONT%;
}
.slots .s.left .t { text-align: left; }
.slots .s.right { justify-content: flex-end; }
.slots .s.right .t { text-align: right; }
"""

# 自适应缩放：浏览器实测 scrollHeight/clientHeight → 缩字号到刚好放下。
# 这一条替代了原来的 wrap_text 估算 + CALIB 校准 + textLength 注入 + 契约字数上限。
DOM_AUTOFIT_JS = """
<script>
(function () {
  document.querySelectorAll('.slots .s .t').forEach(function (el) {
    var box = el.parentElement;                 /* .s —— 槽的固定尺寸 */
    var min = parseFloat(el.dataset.min || '15');
    var fs = parseFloat(getComputedStyle(el).fontSize);
    var guard = 0;
    /* ★ 必须和**槽盒子**比：.t 的高度是内容撑开的，拿它自己比永远相等（实测踩过） */
    function tooBig() {
      return el.scrollHeight > box.clientHeight + 1 || el.scrollWidth > box.clientWidth + 1;
    }
    while (fs > min && guard++ < 80 && tooBig()) {
      fs -= 1;
      el.style.fontSize = fs + 'px';
    }
    el.dataset.fitted = fs;
  });
})();
</script>
"""
DENSE = 0.85        # 密集档字号系数：M~P 之间放得下的文案，用这一档渲染


def _reg_ink(kind, x, y, w, h):
    """登记一块"墨迹"的包围盒：文字不该穿过它（line=箭头/frame=外框/box=方框）。"""
    _INK.append({"kind": kind, "x": float(x), "y": float(y),
                 "w": float(w), "h": float(h)})


def note_band(size, lines=1, gap=10):
    """备注需要预留的竖直空间：上沿余量 + 行数 + 下沿余量。

    字形上沿 ≈ 1.05×字号、下沿 ≈ 1.0×字号（实测：38px 字的 rect 高约 50px，
    基线在中间偏下）。余下的 6px 是呼吸位。
    """
    return int(gap + 1.05 * size + (lines - 1) * 1.34 * size + 1.0 * size + 6)


def note_baseline(default_y, size, lines=1, gap=10):
    """备注基线的**下限**：让首行字形的顶边落在已登记方框的下沿之下。

    实测教训：只保证"基线低于方框下沿"是不够的 —— cover / chain / compare 三处
    备注都因此压在方框下边框上（几何门的 crosses-box），肉眼很容易漏。
    下沿取自 _INK 登记表（浏览器里量出来的几何），所以不依赖任何手写常数。
    """
    bottoms = [b["y"] + b["h"] for b in _INK if b["kind"] == "box"]
    deep = max(bottoms) if bottoms else 0.0
    need = gap + 1.05 * size + (lines - 1) * 0.67 * size
    return max(default_y, deep + need)


def _reg_cap(tag, text, size, maxw, max_lines=1):
    """登记一个文字槽的几何（折行前的原文 + 设计字号 + 可用宽 + 行数上限）。"""
    if maxw is None:
        return
    _CAPS.append({"tag": tag or "?", "text": strip_hl(str(text or "")),
                  "size": int(size), "maxw": float(maxw),
                  "max_lines": int(max_lines or 1)})

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
    _reg_ink("box", x, y, w, h)
    d = hrect_path(x, y, w, h, seed)
    out = "" if not fill else "<path d='%s' fill='%s'/>" % (d, fill)
    # 包 <g data-ink='box'>：几何门在浏览器里 querySelector 量**真实画出来的**范围
    # （手绘笔锋会 overshoot 1~7px，名义 rect 和画出来的线不是一回事）
    return "<g data-ink='box'>%s</g>" % (out + pen_path(pen_rect(x, y, w, h, seed)))


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
    _reg_ink("line", min(x1, x2) - 2, min(y1, y2) - 2,
             abs(x2 - x1) + 4, abs(y2 - y1) + 4)
    d = hand_line(x1, y1, x2, y2, seed, seg=8, amp=1.6, over=0)
    return ("<g data-ink='line'><path d='%s' fill='none' stroke='%s' stroke-width='%.1f' "
            "stroke-linecap='round' marker-end='url(#%s)'/></g>" % (d, INK, SW_ARROW, mid))


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
    # 外框线本身要登记：文字压到卡框是肉眼可见缺陷，用 rect 求交就能抓
    _reg_ink("frame", 26 - 7, 26 - 7, W_CARD - 52 + 14, H_CARD - 52 + 14)
    segs = pen_rect(26, 26, W_CARD - 52, H_CARD - 52, seed, amp=2.0, over=(2.0, 7.0))
    return ("<svg class='frame' data-ink='frame' width='%d' height='%d' viewBox='0 0 %d %d' "
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


def txt(x, y, s, size=SIZES["body"], anchor="middle", fill=C_TEXT,
        maxw=None, tag="", family=None, weight=None, textlength=None, cap=True):
    # 非法 anchor 会静默回退成 start（文字位置整个偏掉，肉眼很难发现）→ 宁可当场炸
    if anchor not in ("start", "middle", "end"):
        raise ValueError("text-anchor 只能是 start/middle/end，收到 %r（center→middle，left→start）"
                         % anchor)
    if True:      # DOM 文字模式：只登记槽，不画 SVG 文字（旧 SVG 实现已删）
        # 自动登记为 DOM 槽：矩形由本函数的参数推导（anchor 决定水平对齐方式）
        _w = maxw or (tw(s, size) * 1.06 + 6)
        _x0 = x - _w / 2.0 if anchor == "middle" else (x if anchor == "start" else x - _w)
        _reg_slot(_x0, y - size * 0.63, _w, size * 1.26, s, size, clamp=1,
                  align={"middle": "center", "start": "start", "end": "right"}[anchor],
                  min_size=max(12, int(size * 0.55)), weight=weight)
        _reg_text(s)
        return ""

def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def wrap_text(s, size, maxw):
    """按可用宽度断行。优先在中文标点/空格处断，断点太靠前才硬断。

    ★ 硬断之前先试"整词换行"：把行尾的拉丁词整体挪到下一行。
    为什么必须有这一步：原来的"断点不够靠前就硬断"用的是**长度比例**判据
    （断点 < len(cur)*0.45 就硬断），短行会因此误判 —— 实测
    `自主 Agent` 在四宫格窄格里：断点处 cur='自主 Ag'（长 5，空格在第 2 位），
    2 < 5*0.45=2.25 → 判为"太靠前" → 硬断成 `自主 Ag` + `ent`，词被劈开。
    中文怎么折都行，拉丁词劈开就是硬伤，所以宁可让上一行短一点。

    判据用的是**完整词**（当前行尾的残词 + 后面接着的拉丁字符），
    因为断点那一刻 cur 里往往只有半个词（'Ag'），拿它判断长度会漏。
    """
    lines, cur, i, n = [], "", 0, len(s)
    while i < n:
        ch = s[i]
        if cur and tw(cur + ch, size) > maxw:
            # ① 整词换行：把完整拉丁词挪到下一行（放得下才挪，避免超长单词空转）
            m = re.search(r"[A-Za-z0-9_\-]+$", cur)
            word = m.group(0) if m else ""
            j = i
            while j < n and re.match(r"[A-Za-z0-9_\-]", s[j]):
                word += s[j]
                j += 1
            if len(word) >= 2 and tw(word, size) <= maxw:
                head = (cur[:m.start()] if m else cur).rstrip()
                if head:                       # 上一行至少留 1 个字；宁可短，别劈词
                    lines.append(head)
                    cur = word
                    i = j
                    continue
            # ② 标点/空格断行（原有行为）
            cut = -1
            for p in "，。；：、,.;:）) ／/":
                cut = max(cut, cur.rfind(p))
            if cut >= len(cur) * 0.45:
                lines.append(cur[:cut + 1])
                cur = cur[cut + 1:].lstrip()   # 新行不吃前导空格
            else:
                # ③ 兜底硬断（超长单词、无标点可断时才会走到这里）
                lines.append(cur)
                cur = ""
        if not cur and ch == " " and lines:
            # 断行已经消费掉那个空格了，别再让新行以空格开头
            # （否则 cur 变成 ' pydantic'，整词换行的 head 判定会误判成"行首空格"）
            i += 1
            continue
        cur += ch
        i += 1
    if cur:
        lines.append(cur)
    return lines


def txt_block(cx, y, s, size=SIZES["note"], maxw=None, fill=C_NOTE,
              line_h=None, max_lines=None, tag="", align="center"):
    """居中多行文本。超出 max_lines 时最后一行补省略号，绝不让字号缩到看不清。"""
    if not s:
        return ""
    maxw = maxw or W_INNER
    # ★ 登记**折行前**的原文。内容门是拿登记串去图上找，如果只登记"渲染出来的行"，
    # 引擎把尾巴截成「…」时两边都是半句话，门永远发现不了截断
    # （实测踩过：timeline 节点说明「…个簇，只扫最近的簇」被吃掉后半句，门报干净）。
    _reg_text(s)
    if True:      # DOM 文字模式：整块登记成一个槽（旧 SVG 实现已删）
        # 高度 = 行数 × 行高，宽度 = maxw
        _n = max_lines or 1
        _h = _n * size * 1.26
        _x0 = cx if align == "start" else cx - maxw / 2.0
        _reg_slot(_x0, y - _h / 2.0, maxw, _h, s, size, clamp=_n,
                  align="start" if align == "start" else "center",
                  min_size=max(12, int(size * 0.55)))
        return ""
    _reg_cap(tag, s, size, maxw, max_lines or 1)
    lines = wrap_text(s, size, maxw)
    if max_lines and len(lines) > max_lines:
        # ★ 多档缩小：小一号不行就再小，直到塞进原定行数 —— **绝不轻易截断**。
        #   为什么要有这个循环：截断 = 丢字 = 必须让 LLM 改文案重跑（实测平均 4 轮）。
        #   而"字小一点"只是观感问题，会在降级报告里点名，不该换来一轮 LLM。
        # 档位加深到 0.42：实测 2 行的槽在 0.42 时容量约翻倍，正常文案不可能再截断。
        # 用户的判断是对的 —— 这是前端/引擎的活，不该把"缩字号"丢回 LLM 改文案。
        for tier in (0.85, 0.78, 0.72, 0.66, 0.60, 0.54, 0.48, 0.42):
            dsize = int(size * tier)
            dlines = wrap_text(s, dsize, maxw)
            if len(dlines) <= max_lines:
                WARN.append("[%s] 密集档 ×%.2f（%dpx，原 %dpx）：折行超限、缩小后塞得下｜%s"
                            % (tag, tier, dsize, size, strip_hl(s)[:34]))
                size, lines = dsize, dlines
                break
    if max_lines and len(lines) > max_lines:
        n_all = len(lines)
        lines = lines[:max_lines]
        lines[-1] = lines[-1][:-1] + "…"
        WARN.append("[%s] 文案被截断：折行后 %d 行、上限 %d 行，尾巴成了「…」｜%s"
                    % (tag, n_all, max_lines, strip_hl(s)[:34]))
    line_h = line_h or size * 1.34
    out = []
    y0 = y - (len(lines) - 1) * line_h * 0.5
    for i, ln in enumerate(lines):
        out.append(txt(cx, y0 + i * line_h, ln, size, fill=fill, tag=tag, cap=False,
                       anchor="start" if align == "start" else "middle"))
    return ""

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


def _reg_text(s):
    """登记一段将写进输出的净文本，供内容门核对。

    为什么需要这道门：文字被静默吞掉时（例如 _inline 漏掉了最后一个 [[高亮]] 之后的
    尾巴，甚至整条副标题变空），**所有几何检查都发现不了** —— 图上根本没有那行字，
    自然也不会溢出、不会压框。这是唯一能抓住「规格写了、图上没有」的门。
    """
    t = re.sub(r"\s+", "", strip_hl(str(s or "")))
    if t:
        _TEXTS.append(t)


def hl_line(cx, y, parts, size=SIZES["body"], seed=1, pad=8, align="center",
            maxw=None, tag=""):
    """一行居中文本，可给任意片段涂蜡笔底色。

    ★ 必须「先画完所有色带、再统一画所有文字」——逐段交替输出时，
      后一段的色带会盖住前一段的文字。

    ★ 文字**必须是一条 <text>**：拆成多条时，每段的 x 要靠 tw() 估算手动推进，
      估算漂移会让相邻段真的压在一起 —— 几何布局门实测抓到
      'MCP' 与 ' 的解法' 重叠 791 px²。色带照旧按估算画（蜡笔笔触本来就有 ±9px
      抖动，漂移看不出来），但文字位置漂移一眼就能看见。
    """
    if True:      # DOM 文字模式：重建高亮标记并登记单槽（旧 SVG 实现已删）
        # parse_hl 已经把 [[…]] 拆成 (文本, 颜色)，这里**重建**成 [[文本|字母]]，
        # 交给 DOM 侧的 _inline 画成 .hl 蜡笔底色（视觉与 SVG 侧一致）。
        _pieces = []
        for _t, _c in parts:
            _pieces.append("[[%s|%s]]" % (_t, _hl_key(_c)) if _c else _t)
        _plain = "".join(_pieces)
        _tw_est = sum(tw(t, size) for t, _ in parts) * 1.06
        _w = maxw or (_tw_est + 12)
        _x0 = cx - _w / 2.0 if align == "center" else cx
        _reg_slot(_x0, y - size * 0.63, _w, size * 1.26, _plain, size, clamp=1,
                  align="center" if align == "center" else "start",
                  min_size=max(12, int(size * 0.55)))
        _reg_text(_plain)
        return ""
    _reg_cap(tag, "".join(t for t, _ in parts), size, maxw, 1)
    total = sum(tw(t, size) for t, _ in parts) * 1.06   # 实际渲染宽估计
    if maxw and total > maxw:
        dense = int(size * DENSE)
        dtotal = sum(tw(t, dense) for t, _ in parts) * 1.06
        if dtotal <= maxw:
            WARN.append("[%s] 密集档 %dpx（原 %dpx）：标准放不下、小一号放得下｜%s"
                        % (tag, dense, size, "".join(t for t, _ in parts)[:34]))
            size = dense
            total = dtotal
        else:
            size = max(20, int(size * maxw / total))
            total = sum(tw(t, size) for t, _ in parts) * 1.06
    x = cx - total / 2.0 if align == "center" else cx
    bands = []
    for i, (t, col) in enumerate(parts):
        w = tw(t, size)
        if col:
            # tw() 对拉丁偏低、对中文准确 → 按拉丁占比轻微补偿，不做整体放大
            latin = sum(1 for c in t if ord(c) <= 0x2E80)
            f = 1.0 + 0.08 * (latin / float(max(1, len(t))))
            bands.append(crayon(x + w / 2.0, y - size * 0.26, w * f + pad * 2,
                                size * 1.02, seed + i * 17, col))
        x += w
    # 文字只画一条：整行交给浏览器排，不再按估算逐段推进。
    # ★ align 的取值是给布局代码看的（center/left/right），**不能直接当 text-anchor 用**：
    #   SVG 只认 start/middle/end，"center" 是非法值 → 浏览器静默回退成 start，
    #   文字会从中心一路往右跑（实测越界 493px，几何门报 out-of-canvas）。
    plain = "".join(t for t, _ in parts)
    anc = {"center": "middle", "left": "start", "right": "end"}.get(align, align)
    return ""

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
    # 显式换行的 \n 会被 _reg_text 规范化掉，图上 <br> 也不产生文本，两边一致
    _reg_text(title)
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
    """页头（标题 + 副标题 + stage 间距）占掉多少高度——要按真实可用高度算预算的版式用。

    踩过的坑：bullets 原来写死 `avail_rows = 960`，但真实可用高度会随标题行数变化
    （标题多一行就少 ~100px），于是 5 条的两行标题页会超出 12px 被门拦下。
    这里按渲染时的同一套几何推导，和 CSS 保持同源。

    另一处坑：显式写 `\\n` 的标题要按**最长的一行**算字号（h1_html 就是这么做的），
    按整条标题估会算小字号 → 页头高度算矮 → 版式又顶破卡片底部。
    """
    title = card.get("title", "") or ""
    lines = title.count("\n") + 1
    size = SIZES["h1"]
    widest = max(title.split("\n"), key=lambda t: tw(t, size)) if "\n" in title else title
    est = tw(widest, size) * 1.06
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
    # 备注预留高度按「字形需要多少」算（原来写死 54，而 38px 字光上沿就要 40px）
    note_h = note_band(SIZES["note"], 1) if card.get("note") else 0
    # 四宫格的高度**必须按真实页头算**。原来写死 890/944：标题一折成两行（或副标题长一点），
    # stage 就顶破卡片底部，而 .card 是 overflow:hidden —— 底部被静默裁掉，
    # measure（只量横向溢出）和肉眼都容易漏。这里改成按真实预算算高度。
    budget = H_CARD - 2 * PAD_TOP - header_height(card)
    grid_h = int(min(890, budget - note_h))
    if grid_h < 560:
        WARN.append("[cover] 可用高度只剩 %dpx：标题/副标题太长，四宫格会被压扁；"
                    "建议精简标题，或改用 hub 版式" % grid_h)
        grid_h = 560
    stage_h = grid_h + note_h
    tw_ = (bw - g) // 2
    th_ = (grid_h - g) // 2
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
        # 基线：默认放在预留带里，但**必须**低于四宫格最深方框的下沿 + 字形上沿余量
        ny = note_baseline(grid_h + note_h - 1.0 * SIZES["note"],
                           SIZES["note"], 1)
        parts.append(txt_block(W_INNER / 2, ny, strip_hl(card["note"]),
                               SIZES["note"], W_INNER, max_lines=1, tag="cover-note"))
    parts.append("</svg>")
    return ("<svg class='stage' width='%d' height='%d' viewBox='0 0 %d %d' "
            "xmlns='http://www.w3.org/2000/svg'>%s"
            % (W_INNER, stage_h, W_INNER, stage_h, "".join(parts)))


def layout_chain(card, seed):
    """竖向步骤链：每个方框都上色，颜色按页轮换。"""
    steps = card.get("steps", [])
    pal = Palette(seed)
    n = max(1, len(steps))
    avail = 900
    note = card.get("note")
    # 备注（最多两行）真正需要的空间：原来只留 76px，而两行 38px 字连字形上沿就要 100px+
    nb = note_band(SIZES["note"], 2) if note else 0
    band = avail - nb
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
        # ★ DOM 文字（阶段②）：只给"框"，折行/居中/缩放交给浏览器。
        #   框已上色时去掉 [[高亮]] —— 色带和框色打架，这条规则与 SVG 模式一致。
        _reg_slot(bx + 16, y + 12, bw - 32, bh - 24,
                  strip_hl(st.get("text", "")) if fill else st.get("text", ""),
                  SIZES["body"], clamp=1, min_size=20)
        if i < n - 1:
            parts.append(v_arrow(W_INNER / 2, y + bh, y + step - 2, "a0", i * 13 + 3))
    if note:
        ny = note_baseline(avail - nb + 1.05 * SIZES["note"] + 0.67 * SIZES["note"] + 10,
                           SIZES["note"], 2)
        _reg_slot(0, ny - 48, W_INNER, 96, strip_hl(note),
                  SIZES["note"], clamp=2, min_size=20)
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
                            seed + 5, 2.0, None))           # 箭头底色：透明（原来填白）
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
            # ★ 说明要压在标题下方：标题字号 42、基线在 y-10，两行说明会把首行上移
            # line_h/2，用 y+36 时说明顶部（y-7.5）会穿到标题底部（y-0.8）里 —— 实测压字。
            parts.append(txt_block(cx, y + 48, strip_hl(st["desc"]), 30, col_w,
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
    if n > 4:
        # ★ 用户要求：flow 节点 ≤4，超过就换版式（5 个时每格只剩 ~116px、
        #   标签只能放 2 个汉字，怎么调都不好看）
        WARN.append("[flow] 节点 %d 个超过 4：格宽不足以放下标签，**建议改用 chain（竖向）"
                    "或 bullets（清单）**；仍按 flow 渲染但会偏挤" % n)
    avail = 900
    bx = BOX_INSET
    bw = W_INNER - 2 * bx
    gap = 26
    w = (bw - gap * (n - 1)) // n
    bh = 176

    # ★ 竖向自适应（实测：flow 页底部空 287px，占画布 32%，九个版式里最空的）
    #   原来 top 写死 170，而"节点行 + 说明 + 备注"整块远比画布矮。两个要点：
    #     ① 备注高度按**真实折行数**算 —— 早先按最坏情况（2 行）估，实际都 1 行，
    #        算出来的 top 只从 170 动到 166，等于没改（这就是第一版白改的原因）；
    #     ② 余量要**分给节点高度**，光居中填不了空（内容本身就矮）。
    def _note_h(text, size, max_lines):
        if not text:
            return 0
        lines = min(len(wrap_text(strip_hl(text), size, W_INNER)), max_lines)
        return int(lines * size * 1.34 + 12)

    notes_h = (_note_h(card.get("note"), SIZES["body"] - 6, 2)
               + _note_h(card.get("note2"), SIZES["note"], 2))
    # ★ mid（顶部灰色说明）原来写死 y=104，而节点区的 top 是自适应的 ——
    #   两者相撞：实测文字 y=62~114 与方框 y=108 起重叠（crosses-box）。
    #   现在它也纳入块高：先算整块（mid + 节点行 + 备注 + bottom），再统一居中。
    mid_h = int(SIZES["note"] * 1.34) + 26 if card.get("mid") else 0
    # ★ bottom（底部那排小框）必须**参与块高计算**，不能写死 y=700：
    #   节点区和备注是自适应的，写死坐标一定会在某组参数下相撞。
    has_bottom = bool(card.get("bottom"))
    bottom_h = 190 if has_bottom else 0
    block_h = mid_h + bh + 108 + notes_h + bottom_h
    slack = avail - block_h
    if slack > 60:                       # 有富余就把节点框拔高（上限 90，别撑变形）
        bh += min(90, int(slack * 0.45))
        block_h = mid_h + bh + 108 + notes_h + bottom_h
    block_top = max(24, int((avail - block_h) / 2.0))
    top = block_top + mid_h
    parts = [defs("a0")]
    if card.get("dashed"):
        parts.append(dash_box(bx - 8, top - 56, bw + 16, bh + 84, seed + 99,
                              card.get("dashed_label")))
    # ★ flow 的文字**全部走 DOM**（阶段①：迁移完成，SVG 文字分支已删除）。
    #   为什么删：折行/行数上限/垂直居中/自适应缩放交给浏览器后，孤字、劈词、压框线、
    #   容量随数量变化这一整类问题都不再是"引擎算出来的" —— 原来那套 wrap_text/fit/
    #   契约字数上限对 flow 已经没有意义。字体在这里只是"起手字号"，缩多少由 JS 实测决定。
    for i, nd in enumerate(nodes):
        x = bx + i * (w + gap)
        fill = PAL.get(nd.get("fill")) or pal.next()
        parts.append(pen_box(x, top, w, bh, i * 15 + 3, fill))
        _reg_slot(x + 12, top + 12, w - 24, 54, strip_hl(nd.get("text", "")),
                  SIZES["body"] - 10, clamp=1)
        if nd.get("desc"):
            _reg_slot(x + 13, top + 70, w - 26, bh - 84, strip_hl(nd["desc"]),
                      26, clamp=2, min_size=13)
        if i < n - 1:
            parts.append(arrow(x + w, top + bh / 2, x + w + gap, top + bh / 2,
                               "a0", i * 19 + 2))
    y = top + bh + 108
    if card.get("mid"):
        _reg_slot(0, block_top + 2, W_INNER, mid_h - 6, strip_hl(card["mid"]),
                  SIZES["note"], clamp=2, min_size=18)
    if card.get("note"):
        _reg_slot(0, y - 45, W_INNER, 90, strip_hl(card["note"]),
                  SIZES["body"] - 6, clamp=2, min_size=20)
        # ★ 原来只 += 58：上一条的**末行基线**到下一条的**首行基线**实际只差 9px，
        # 两行字真的叠在一起（几何门实测重叠 6971px²）。
        # 要按"上一条的块高 + 下一条字形上沿"算：0.67×s1（2 行的块半高）+ 1.05×s2 + 0.67×s2 + 10
        y += int(0.67 * (SIZES["body"] - 6) + note_band(SIZES["note"], 2) - 0.67 * SIZES["note"])
    if card.get("note2"):
        _reg_slot(0, y - 48, W_INNER, 96, strip_hl(card["note2"]),
                  SIZES["note"], clamp=2, min_size=20)
    bottom = card.get("bottom") or []
    if bottom:
        m = len(bottom)
        # y 由内容推出来（备注之下 30px），不再写死 700；越界时贴底兜底
        by = top + bh + 108 + notes_h + 30
        if by + 150 > avail - 10:
            by = max(110, avail - 160)
        cwid = (bw - (m - 1) * 24) // m
        for i, c in enumerate(bottom):
            x = bx + i * (cwid + 24)
            parts.append(pen_box(x, by, cwid, 150, i * 23 + 5,
                                 PAL.get(c.get("fill")) or pal.next()))
            _reg_slot(x + 12, by + 18, cwid - 24, 56, strip_hl(c.get("text", "")),
                      36, clamp=1, min_size=18)
            if c.get("desc"):
                _reg_slot(x + 13, by + 74, cwid - 26, 64, strip_hl(c["desc"]),
                          26, clamp=2, min_size=13)
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
        if plain:
            # 这一支用 esc 直接拼 HTML，绕过了 _inline → 要手动登记，
            # 否则内容门对「已上色行」的文字失明
            _reg_text(it.get("head", ""))
            _reg_text(it.get("desc", ""))
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
    _reg_text(text)
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
    # 有备注时两列压矮 30px：备注（两行 34px 字）需要 ~110px，原来 760+56 会压到列下沿
    has_note = bool(left.get("note") or right.get("note"))
    box_y, box_h, pad = 90, (730 if has_note else 760), 36

    def col(cfg, x0, seed0):
        g = []
        # ★ DOM 文字（阶段②）：列标题、块文字、备注全部登记为 slot
        _reg_slot(x0 + 4, 22, col_w - 8, 60, cfg.get("label", ""), 44,
                  clamp=1, min_size=22)
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
            # 框已上色时去掉 [[高亮]]（色带与框色打架），与 SVG 模式规则一致
            _reg_slot(x0 + 36, y + 8, col_w - 84, bh - 16,
                      strip_hl(text) if f not in (None, "none") else text,
                      34, clamp=2, min_size=16)
        if cfg.get("note"):
            ny = note_baseline(box_y + box_h + 56, 34, 2)
            _reg_slot(x0, ny - 44, col_w, 88, strip_hl(cfg["note"]),
                      34, clamp=2, min_size=18)
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
        _reg_text(lab["left"])
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

# 用户要求：删掉一种齿轮（gear2f1），新增蓝色云朵
DECO_VARIANTS = ["gear1", "gear2", "gear2f2", "star4", "star5", "star5f", "cloud"]
DECO_SLOTS = [[(952, 64), (958, 692), (58, 1248)],
              [(46, 64), (958, 692), (948, 1248)]]


def _deco_layer(idx):
    from decor import decor
    parts = ["<svg class='deco' width='%d' height='%d' viewBox='0 0 %d %d' "
             "xmlns='http://www.w3.org/2000/svg'>" % (W_CARD, H_CARD, W_CARD, H_CARD)]
    nv = len(DECO_VARIANTS)
    variants = [DECO_VARIANTS[(idx * 1) % nv], DECO_VARIANTS[(idx * 2 + 3) % nv],
                DECO_VARIANTS[(idx * 3 + 5) % nv]]
    slots = DECO_SLOTS[idx % 2]
    for i, (name, (x, y)) in enumerate(zip(variants, slots)):
        size = (24, 27, 30)[i]          # 用户要求：装饰小一点（原 30/34/38）
        pair = name.startswith("gear2")
        if pair:
            x -= size * 1.05
        lo, hi = 30 + size * 1.05, W_CARD - 32 - (size * 1.25 if pair else size)
        x = max(lo, min(hi, x))
        y = max(24 + size * 1.15, min(H_CARD - 24 - size * 1.15, y))
        # 透明度 +30%（0.42/0.46 × 0.7）：装饰不能抢正文
        parts.append(decor(name, x, y, size, 300 + i * 7 + idx,
                           0.29 if pair else 0.32))
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
    _TEXTS.clear()
    _CAPS.clear()
    _INK.clear()
    _SLOTS.clear()
    body = LAYOUTS[layout](card, idx * 17 + 7)
    dom_slots = ""
    dom_js = ""
    if _SLOTS:
        # DOM 文字模式：墨迹照旧是 stage SVG，文字是绝对定位的 HTML，
        # 与 stage 同一坐标系（stagewrap 相对定位 → slots 覆盖在上面）
        items = []
        for s in _SLOTS:
            cls = "s left" if s["align"] == "left" else "s"
            wgt = "font-weight:%s;" % s["weight"] if s["weight"] else ""
            items.append(
                "<div class='%s' style='left:%.1fpx;top:%.1fpx;width:%.1fpx;height:%.1fpx;"
                "--clamp:%d'>"
                "<div class='t' data-min='%d' style='font-size:%dpx;%s'>%s</div></div>"
                % (cls, s["x"], s["y"], s["w"], s["h"], s["clamp"], s["min"], s["size"],
                   wgt, _inline(s["text"])))
        dom_slots = "<div class='slots'>%s</div>" % "".join(items)
        dom_js = DOM_AUTOFIT_JS
        _reg_text(" ".join(s["text"] for s in _SLOTS))      # 内容门照样登记
        body = "<div class='stagewrap'>%s%s</div>" % (body, dom_slots)
    sub = _sub(card.get("subtitle", ""))
    h1 = h1_html(card.get("title", ""))
    foot = meta.get("footer", "")
    foot_html = ""
    if foot:
        _reg_text(foot)
        foot_html = "<div class='foot'>%s</div>" % esc(foot)
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
    if _SLOTS:                       # DOM 文字模式的样式（占位符与主 CSS 同一套替换）
        _dcss = DOM_SLOT_CSS
        for k, v in repl:
            _dcss = _dcss.replace(k, v)
        css += _dcss

    # ★ manifest 必须最后算：上面每个渲染函数都会 _reg_text 登记文字，
    # 早算一步就漏掉后发生的那批（踩过：算在 _sub 之前 → 副标题没进清单，
    # 于是内容门对副标题完全失明）。
    manifest = ("<!--T2I_BOXES:%s--><!--T2I_TEXTS:%s--><!--T2I_CAPS:%s-->"
                "<!--T2I_INK:%s-->") % (
        json.dumps(_BOXES), json.dumps(_TEXTS, ensure_ascii=False),
        json.dumps(_CAPS, ensure_ascii=False), json.dumps(_INK, ensure_ascii=False))
    return ("""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="UTF-8"><style>%s</style></head>
<body><div class="card %s">
%s
%s
%s
%s
%s
%s
%s
</div>%s</body></html>""" % (css, cls, manifest, frame_overlay(kind, 4200 + idx),
                           deco, h1, sub, body, foot_html, dom_js))
