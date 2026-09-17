# -*- coding: utf-8 -*-
"""vision_probe.py —— 读图能力判定（多模态自检的可复现版本）

为什么需要它：模型对图片的支持有三种状态，**不是两种**：

  1. **能读**：说得出图里的具体内容 → 可以做审美终检
  2. **静默丢图**：请求 200、回答流畅，但模型**根本没看到图** —— **这一类最危险**：
     Agent 会误以为"我已经看过图了"，然后在交付报告里写"视觉已校验"，实际是假的
  3. **纯文本**：读图工具直接报错 → 老实跳过

判定不能靠"harness 有没有声明图片支持"，必须**真读一张已知内容的图**，
并要求模型说出图里的**具体内容**。

探针图是 skill 的**固定资产**：`assets/vision-probe.png`
（红底 + 白色三角形 + 黑色横条，512×512，约 2KB）。它随仓库分发，理由：
  - 内容恒定且**可人工审阅**（打开看一眼就知道该答什么，判定才公平）
  - 跨用户/跨环境完全一致，不会因为重新生成而漂移
  - 离线可用、不往工作区写临时文件

用法
    python scripts/vision_probe.py                 # 打印探针图路径 + 该问什么
    python scripts/vision_probe.py --check "<模型的回答>"   # 校验答案
    python scripts/vision_probe.py --remake        # 重新生成资产（维护用）

零依赖：PNG 用标准库 zlib 手写，不依赖 Pillow。
"""
import argparse
import io
import os
import struct
import sys
import zlib

W = H = 512
RED = (222, 51, 51)
WHITE = (255, 255, 255)
BLACK = (17, 17, 17)

HERE = os.path.dirname(os.path.abspath(__file__))
ASSET = os.path.join(os.path.dirname(HERE), "assets", "vision-probe.png")


def _write_png(path, rows):
    """把 (r,g,b) 像素行写成 PNG。标准库实现，避免引入 Pillow。"""
    raw = b"".join(b"\x00" + bytes(v for px in row for v in px) for row in rows)

    def chunk(tag, data):
        body = tag + data
        return (struct.pack(">I", len(data)) + body
                + struct.pack(">I", zlib.crc32(body) & 0xffffffff))

    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0))
           + chunk(b"IDAT", zlib.compress(raw, 9))
           + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def _in_triangle(x, y):
    """识别用的白色三角形：顶点在上，底边在下。"""
    cx, top, bot, half = W / 2.0, 120, 380, 190
    if not (top <= y <= bot):
        return False
    t = (y - top) / float(bot - top)
    return abs(x - cx) <= half * t


def make(path=None):
    """生成探针图（确定性：同样参数永远得到同样的图）。"""
    path = path or ASSET
    d = os.path.dirname(path)
    if d and not os.path.isdir(d):
        os.makedirs(d)
    rows = []
    for y in range(H):
        row = []
        for x in range(W):
            px = RED
            if _in_triangle(x, y):
                px = WHITE
            elif 430 <= y <= 470:                 # 底部黑条
                px = BLACK
            row.append(px)
        rows.append(row)
    _write_png(path, rows)
    return path


# 判定规则：必须同时说出「红色」和「三角形」。
# 只答"一张图/一张图片/红色"都不算——那正是静默丢图的表现。
NEED = [("红", "red", "红的"), ("三角", "triangle")]


def check(answer):
    low = (answer or "").lower()
    hits = [any(k in low for k in group) for group in NEED]
    if all(hits):
        return True, "✅ 能读图（说对了背景色和中间形状）"
    if any(hits):
        return False, "❌ 只答对一半：疑似看到了但没看清，按「不能读」处理更安全"
    return False, ("❌ 判为不能读图：答案里既没有「红」也没有「三角」——"
                   "这正是**静默丢图**：请求成功、回答流畅，但模型根本没看到图。")


def main():
    ap = argparse.ArgumentParser(description="读图能力判定")
    ap.add_argument("--check", default=None, help="校验模型的答案，传它的原文")
    ap.add_argument("--remake", action="store_true", help="重新生成探针图资产（维护用）")
    args = ap.parse_args()

    if args.check is not None:
        ok, msg = check(args.check)
        print(msg)
        if not ok:
            print()
            print("处置：")
            print("  1) 先确认 harness 是否声明了该模型的图片输入能力（这是最常见的原因）")
            print("  2) 声明了还是这样 → 按**纯文本**路径走，跳过审美终检")
            print("  3) 交付时如实说明「审美未校验」，不要写「已视觉检查」")
        return 0 if ok else 1

    if args.remake:
        p = make()
        print("已重新生成：%s（%d bytes）" % (p, os.path.getsize(p)))
        return 0

    if not os.path.exists(ASSET):
        p = make()
        print("资产缺失，已重新生成：%s" % p)
    print("探针图（skill 自带资产）：%s" % ASSET)
    print()
    print("接下来让模型读这张图，问它：")
    print("  「这张图的背景是什么颜色？中间是什么形状？底部还有什么？」")
    print()
    print("然后把模型的回答原样交给校验：")
    print('  python scripts/vision_probe.py --check "<模型的回答>"')
    print()
    print("判定标准：必须同时说出【红色】和【三角形】。")
    print("只答「一张图」「一张红色图片」之类 → 视为静默丢图，按不能读图处理。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
