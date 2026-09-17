# -*- coding: utf-8 -*-
"""手绘装饰零件库 —— 固定一套，复用，不要每次重新推。

零件清单（按用户 2026-09-17 02:00 定的：只要齿轮和星，不要箭头 / 大脑 / 波浪）

    齿轮系
      gear1    单齿轮 · 空心
      gear2    双齿轮 · 空心
      gear2f1  双齿轮 · 小的那个蜡笔灰填充
      gear2f2  双齿轮 · 两个都蜡笔灰填充
    星系
      star4    四角星 · 空心
      star5    五角星 · 空心
      star5f   五角星 · 蜡笔黄填充

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

_uid = [0]


def _nid():
    _uid[0] += 1
    return "dc%d" % _uid[0]


def _rnd(seed):
    return random.Random(seed + 404)


def _jk(pts, seed, amp):
    r = _rnd(seed)
    return [(x + r.uniform(-amp, amp), y + r.uniform(-amp, amp)) for x, y in pts]


def _shape(pts, seed, amp, w=SW * 0.55, op=0.55, fill=None, color=INK):
    """闭合手绘形状；fill 不为空时叠一层「蜡笔填充」（实色 + 白斜纹）。"""
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


DECOR = {
    "gear1": gear1,
    "gear2": gear2,
    "gear2f1": gear2f1,
    "gear2f2": gear2f2,
    "star4": star4,
    "star5": star5,
    "star5f": star5f,
}

DESC = {
    "gear1": "单齿轮 · 空心",
    "gear2": "双齿轮 · 空心",
    "gear2f1": "双齿轮 · 小的蜡笔灰",
    "gear2f2": "双齿轮 · 都蜡笔灰",
    "star4": "四角星 · 空心",
    "star5": "五角星 · 空心",
    "star5f": "五角星 · 蜡笔黄",
}


def decor(name, x, y, size, seed=1, opacity=None):
    """按名字取装饰；opacity 不传就用该零件的默认值。"""
    fn = DECOR[name]
    return fn(x, y, size, seed) if opacity is None else fn(x, y, size, seed, opacity)


if __name__ == "__main__":
    print("装饰零件（%d 种）：" % len(DECOR))
    for k in DECOR:
        print("  %-9s %s" % (k, DESC[k]))
