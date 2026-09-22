# -*- coding: utf-8 -*-
"""手绘装饰零件库 —— 固定一套，复用，不要每次重新推。

零件清单（按用户 2026-09-17 02:00 定的：只要齿轮和星，不要箭头 / 大脑 / 波浪）

    齿轮系
      gear1    单齿轮 · 空心
      gear2    双齿轮 · 空心
      gear2f2  双齿轮 · 两个都蜡笔灰填充
    星系
      star4    四角星 · 空心
      star5    五角星 · 空心
      star5f   五角星 · 蜡笔黄填充
    云
      cloud    云朵 · 蜡笔蓝填充（2026-09-18 新增）

设计约定
  1. 纯 SVG path/line，无位图、无文字，可任意放缩
  2. 统一 INK 暖灰描边；空心件描边透明度默认 0.55（装饰不能抢正文）
  3. 填充件用「实色 + 白色斜纹」模拟蜡笔涂写，不是死板的纯色块
  4. 签名统一 (x, y, size, seed=1, opacity=None)，x/y 是视觉中心
  5. 手绘抖动幅度随 size 缩放（写死会在小尺寸抖变形）
  6. clipPath 的 id 用全局计数器生成，避免同页多个填充件撞 id

用法
    from decor import decor, DECOR
    svg += decor("gear2f1", 952, 1246, 40)
"""
import math
import random

INK = "#5C584F"
SW = 6.0
CRAYON_GRAY = "#CFCBC0"
CRAYON_YELLOW = "#FFE04D"
CRAYON_BLUE = "#7FCBEF"      # 云朵：用户指定用蓝色涂

# 主题钩子：ink.py 画装饰层之前会调 set_style()，把当前主题的墨迹色与抖动倍率塞进来。
# ★ 装饰件也必须跟着主题走：深底上留一个暖灰齿轮，比不画还难看。
AMP = 1.0                    # 抖动倍率（0 = 几何直线/正圆）
_uid = [0]


def set_style(ink=None, amp=None, sw=None):
    """由 ink.py 在画装饰层前调用：换描边色 / 抖动倍率 / 线宽。

    注意 `_shape(..., color=None)` 是**调用时**回落到 INK 的（不是 def 期绑定），
    所以这里改 INK 立刻生效；写成 `color=INK` 那种默认参数就换不动了。
    """
    global INK, AMP, SW
    if ink is not None:
        INK = ink
    if amp is not None:
        AMP = float(amp)
    if sw is not None:
        SW = 6.0 * float(sw)


def _nid():
    _uid[0] += 1
    return "dc%d" % _uid[0]


def _rnd(seed):
    return random.Random(seed + 404)


def _jk(pts, seed, amp):
    r = _rnd(seed)
    return [(x + r.uniform(-amp, amp) * AMP, y + r.uniform(-amp, amp) * AMP)
            for x, y in pts]


def _shape(pts, seed, amp, w=None, op=0.55, fill=None, color=None):
    """闭合手绘形状；fill 不为空时叠一层「蜡笔填充」（实色 + 白斜纹）。

    `color=None` 表示"用当前主题的墨迹色"，`w=None` 表示"跟随当前线宽"——
    **不能写成 `color=INK`**：默认参数是 def 期绑定，主题换了也换不动。
    """
    if color is None:
        color = INK
    if w is None:
        w = SW * 0.55
    j = _jk(pts, seed, amp)
    d = "M" + " L".join("%.1f %.1f" % q for q in j) + " Z"
    out = []
    if fill:
        cid = _nid()
        out.append("<clipPath id='%s'><path d='%s'/></clipPath>" % (cid, d))
        out.append("<path d='%s' fill='%s' fill-opacity='0.62'/>" % (d, fill))
        xs = [p[0] for p in j]
        ys = [p[1] for p in j]
        x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)
        hatch = []
        n = 5
        for i in range(n):
            yy = y0 + (y1 - y0) * (i + 0.5) / n
            hatch.append("<line x1='%.1f' y1='%.1f' x2='%.1f' y2='%.1f'/>"
                         % (x0 - 8, yy + 3, x1 + 8, yy - 5))
        out.append("<g clip-path='url(#%s)' stroke='#FFFFFF' stroke-opacity='0.30' "
                   "stroke-width='%.1f' stroke-linecap='round'>%s</g>"
                   % (cid, w * 1.5, "".join(hatch)))
    out.append("<path d='%s' fill='none' stroke='%s' stroke-width='%.2f' stroke-opacity='%.2f' "
               "stroke-linecap='round' stroke-linejoin='round'/>" % (d, color, w, op))
    return "".join(out)


# ---------------------------------------------------------------- 齿轮
def _gear_pts(x, y, size, teeth=9):
    """梯形齿齿轮的采样点：每齿 4 点（根-尖-尖-根），齿高约 26%。

    踩过的坑：早先用「圆 + 一圈放射线」拼，那个形状是太阳，不是齿轮。
    齿轮的本质是齿为梯形凸起、根部圆弧过渡的**一条闭合轮廓**。
    """
    rt, rr = size * 1.00, size * 0.74
    step = 2 * math.pi / teeth
    pts = []
    for i in range(teeth):
        a0 = i * step
        for da, rad in ((-step * 0.30, rr), (-step * 0.185, rt),
                        (step * 0.185, rt), (step * 0.30, rr)):
            pts.append((x + rad * math.cos(a0 + da), y + rad * math.sin(a0 + da)))
    return pts


def _gear(x, y, size, seed, op, fill=None, teeth=9):
    """一个齿轮 = 闭合齿廓 + 轮毂圆 + 轴心点。"""
    out = [_shape(_gear_pts(x, y, size, teeth), seed, size * 0.028, SW * 0.62, op, fill)]
    out.append("<circle cx='%.1f' cy='%.1f' r='%.1f' fill='none' stroke='%s' stroke-width='%.2f' "
               "stroke-opacity='%.2f'/>" % (x, y, size * 0.30, INK, SW * 0.55, op))
    out.append("<circle cx='%.1f' cy='%.1f' r='%.1f' fill='%s' fill-opacity='%.2f'/>"
               % (x, y, size * 0.10, INK, op * 0.85))
    return "".join(out)


def gear1(x, y, size, seed=1, opacity=0.55):
    """单齿轮 · 空心。"""
    return _gear(x, y, size, seed, opacity)


def _gear_pair(x, y, size, seed, opacity, fill_big=None, fill_small=None):
    """一大一小两个啮合齿轮：小的挂在右下 45° 方向。"""
    sx, sy = x + size * 1.32, y + size * 0.96
    ssz = size * 0.58
    return (_gear(sx, sy, ssz, seed + 21, opacity, fill_small, teeth=8)
            + _gear(x, y, size, seed, opacity, fill_big))


def gear2(x, y, size, seed=1, opacity=0.55, variant=0):
    """双齿轮。variant: 0 全空心 / 1 小的填充 / 2 两个都填充。"""
    return _gear_pair(x, y, size, seed, opacity,
                      CRAYON_GRAY if variant == 2 else None,
                      CRAYON_GRAY if variant in (1, 2) else None)


def gear2f1(x, y, size, seed=1, opacity=0.55):
    """双齿轮 · 小的那个蜡笔灰填充。"""
    return gear2(x, y, size, seed, opacity, variant=1)


def gear2f2(x, y, size, seed=1, opacity=0.55):
    """双齿轮 · 两个都蜡笔灰填充。"""
    return gear2(x, y, size, seed, opacity, variant=2)


# ---------------------------------------------------------------- 星
def star4(x, y, size, seed=1, opacity=0.55, fill=None):
    """四角星：外尖内凹（八点交替，步进 45°）。"""
    pts = []
    for i in range(8):
        ang = math.pi / 4 * i - math.pi / 2
        rad = size if i % 2 == 0 else size * 0.24
        pts.append((x + rad * math.cos(ang), y + rad * math.sin(ang)))
    return _shape(pts, seed, size * 0.045, SW * 0.52, opacity, fill)


def star5(x, y, size, seed=1, opacity=0.55, fill=None):
    """五角星：十点交替，步进 36°。"""
    pts = []
    for i in range(10):
        ang = math.pi / 5 * i - math.pi / 2
        rad = size if i % 2 == 0 else size * 0.42
        pts.append((x + rad * math.cos(ang), y + rad * math.sin(ang)))
    return _shape(pts, seed, size * 0.035, SW * 0.52, opacity, fill)


def star5f(x, y, size, seed=1, opacity=0.62):
    """五角星 · 蜡笔黄填充。"""
    return star5(x, y, size, seed, opacity, fill=CRAYON_YELLOW)


def cloud(x, y, size, seed=1, opacity=0.55):
    """云朵 · 蓝色蜡笔填充（用户指定）。

    形状 = **几个椭圆瓣按上包络取并集 + 平底**。像不像云，全看两件事：

    1. **瓣的圆心高度要错落**。等高的一圈圆瓣并集是**土坡**，不是云 ——
       这是返工三次才想明白的：平底 + 等高的圆瓣，包与包之间几乎不出凹口，
       因为小瓣的顶永远低于它与大瓣的交点（推导过：要出凹口就得把宽度拉到
       3 倍以上）。把中间那瓣**抬高**之后，高度差直接造出肩部凹口，
       宽度还不用变。
    2. **采样点要少**（22~26 个）。`_jk` 是逐点独立抖动的，点数一多就成高频
       锯齿、弧感全没（实测 57 点 + amp 0.05 → 顶边像石头；星形只用 10 点）。

    返工记录：旧版 `rad = size*(0.60 + 0.30*sin(3θ))` 绕一圈 → 一团三瓣圆球；
    改"圆心落在基线上"→ 有了平底但太扁（长宽比 2.7，像土坡）；
    最后改成椭圆瓣 + 抬高中间瓣（长宽比约 2.0）才成形。
    """
    base = y + size * 0.46                       # 底边：云是平底，中心对齐 (x, y)
    # (横向偏移, 圆心抬高, 半宽 a, 半高 b)，单位 size
    lobes = [(-0.50, 0.30, 0.46, 0.46),
             (0.05, 0.52, 0.42, 0.42),
             (0.56, 0.28, 0.38, 0.38)]
    cs = [(x + dx * size, base - up * size, a * size, b * size) for dx, up, a, b in lobes]
    x0 = min(cx - a for cx, _cy, a, _b in cs)             # 形状实际左右边界
    x1 = max(cx + a for cx, _cy, a, _b in cs)
    pts = []
    n = 26
    for i in range(n + 1):
        px = x0 + (x1 - x0) * i / n
        top = base
        for cx, cy, a, b in cs:                           # 上包络：取所有瓣里最高的
            d = abs(px - cx)
            if d < a:
                top = min(top, cy - b * math.sqrt(1.0 - (d / a) ** 2))
        pts.append((px, top))
    # ★ 底边补几个点：只留一条直线边的话，_jk 的抖动只作用在两端，
    #   底边会是一条笔直的线，和手绘轮廓不搭。
    for i in range(4, -1, -1):
        pts.append((x0 + (x1 - x0) * i / 5.0, base))
    return _shape(pts, seed, size * 0.022, fill=CRAYON_BLUE, op=opacity)


# ---------------------------------------------------------------- 极客系
# 目标：深色工程风（终端 / 蓝图 / 北欧）的装饰件。这几种主题**抖动为 0**，
# 所以零件本身必须就是几何图形，不能靠手绘抖动出效果。
def _stroke(d, w, op):
    return ("<path d='%s' fill='none' stroke='%s' stroke-width='%.2f' "
            "stroke-opacity='%.2f' stroke-linecap='square'/>" % (d, INK, w, op))


def plus3(x, y, size, seed=1, opacity=0.55):
    """三个加号 · 像素风（参考图左上角那种 `+++`）。

    加号必须**用 stroke-linecap:square**：圆头加号是"医疗十字"，
    方头才是终端里那种字符感。
    整体占一个 2×size 见方的盒子（和其它零件同一个口径，摆位才好预算）。
    """
    out = []
    arm = size * 0.30
    w = max(2.0, size * 0.15)
    for i in (-1, 0, 1):
        cx = x + i * size * 0.62
        out.append(_stroke("M%.1f %.1f L%.1f %.1f" % (cx - arm, y, cx + arm, y), w, opacity))
        out.append(_stroke("M%.1f %.1f L%.1f %.1f" % (cx, y - arm, cx, y + arm), w, opacity))
    return "".join(out)


# 5×7 点阵的「?」，1 = 点亮。手写点阵而不是用字体：
# 字体渲染出来的问号是曲线，和"像素"这个语义正好相反。
_PIXQ = ["01110",
         "10001",
         "00001",
         "00010",
         "00100",
         "00000",
         "00100"]


def pixq(x, y, size, seed=1, opacity=0.62):
    """像素问号 · 方块拼（参考图右下角那个）。

    点阵宽 5 / 高 7 → 单格边长 = 2×size/7，整体以 (x, y) 为中心。
    """
    c = size * 2.0 / 7.0
    x0 = x - 5 * c / 2.0
    y0 = y - 7 * c / 2.0
    gap = c * 0.10                       # 方块之间留缝，"像素"感全在这条缝上
    out = []
    for r, row in enumerate(_PIXQ):
        for k, ch in enumerate(row):
            if ch == "1":
                out.append("<rect x='%.1f' y='%.1f' width='%.1f' height='%.1f' fill='%s' "
                           "fill-opacity='%.2f'/>"
                           % (x0 + k * c, y0 + r * c, c - gap, c - gap, INK, opacity))
    return "".join(out)


def crosshair(x, y, size, seed=1, opacity=0.5):
    """十字准星：一个圆 + 四条伸出去的短线（蓝图/北欧用）。整体占 2×size。"""
    r = size * 0.58
    ext = size * 1.0
    w = max(1.4, size * 0.075)
    out = ["<circle cx='%.1f' cy='%.1f' r='%.1f' fill='none' stroke='%s' "
           "stroke-width='%.2f' stroke-opacity='%.2f'/>" % (x, y, r, INK, w, opacity)]
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        out.append(_stroke("M%.1f %.1f L%.1f %.1f"
                           % (x + dx * r * 1.15, y + dy * r * 1.15,
                              x + dx * ext, y + dy * ext), w, opacity))
    return "".join(out)


def corners(x, y, size, seed=1, opacity=0.45):
    """四角括线（取景框角）：四个 L 形，整体半宽 size。

    单独用请走 `card_corners()` —— 这件是**整卡**零件，摆在侧边留白带上
    只会看着像一个莫名其妙的方框（实测踩过）。
    """
    w = max(1.8, size * 0.085)
    L = size * 0.85
    out = []
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        px, py = x + sx * size, y + sy * size
        out.append(_stroke("M%.1f %.1f L%.1f %.1f L%.1f %.1f"
                           % (px - sx * L, py, px, py, px, py - sy * L), w, opacity))
    return "".join(out)


def card_corners(w, h, size, opacity=0.4):
    """整卡取景框：四个卡角各一个 L 形括线（蓝图/终端那种工程感角标）。"""
    w_ = max(1.8, size * 0.085)
    L = size * 0.85
    pad = 14.0
    out = []
    for cx, cy, sx, sy in ((pad, pad, 1, 1), (w - pad, pad, -1, 1),
                           (w - pad, h - pad, -1, -1), (pad, h - pad, 1, -1)):
        out.append(_stroke("M%.1f %.1f L%.1f %.1f L%.1f %.1f"
                           % (cx + sx * L, cy, cx, cy, cx, cy + sy * L), w_, opacity))
    return "".join(out)


DECOR = {
    # ★ 用户要求：删掉一种齿轮（gear2f1「小的蜡笔灰」—— 填充件在低透明度下最显脏）
    "gear1": gear1,
    "gear2": gear2,
    "gear2f2": gear2f2,
    "star4": star4,
    "star5": star5,
    "star5f": star5f,
    "cloud": cloud,          # 新增：蓝色云朵
    # 极客系（2026 加主题系统时新增）：给终端 / 蓝图 / 北欧这类深色工程风用
    "plus3": plus3,
    "pixq": pixq,
    "crosshair": crosshair,
    "corners": corners,
}

DESC = {
    "gear1": "单齿轮 · 空心",
    "gear2": "双齿轮 · 空心",
    "gear2f2": "双齿轮 · 都蜡笔灰",
    "star4": "四角星 · 空心",
    "star5": "五角星 · 空心",
    "star5f": "五角星 · 蜡笔黄",
    "cloud": "云朵 · 蜡笔蓝",
    "plus3": "三个加号 · 像素",
    "pixq": "像素问号 · 方块拼",
    "crosshair": "十字准星 · 圆+十字",
    "corners": "四角括线 · 取景框",
}


def decor(name, x, y, size, seed=1, opacity=None):
    """按名字取装饰；opacity 不传就用该零件的默认值。"""
    fn = DECOR[name]
    return fn(x, y, size, seed) if opacity is None else fn(x, y, size, seed, opacity)


if __name__ == "__main__":
    print("装饰零件（%d 种）：" % len(DECOR))
    for k in DECOR:
        print("  %-9s %s" % (k, DESC[k]))
