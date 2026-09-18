# -*- coding: utf-8 -*-
"""review_sheet.py —— 把复核从"逐个分析 2160×2880 原图"变成"看拼版缩略图"。

为什么要有它（实测数据）：hermes 第 1 轮跑一篇，12 次 `vision_analyze` 吃掉 **653 秒 = 总时长的 77%**，
单次 20~236 秒，而且模型每次都写一整段"图像整体描述"。原图 2160×2880 对这个活完全是浪费：
视觉模型拿到图后本来就会缩到长边 1536~2048，token 与延迟都按像素走。

产出：
    review/thumb/card-XX.jpg    720px 宽（要细看单张时用）
    review/sheet-01.jpg         拼版图，每格带 `card-XX` 角标 —— **一次分析看 N 张**

用法：
    python scripts/review_sheet.py <出图目录>                  # 默认 720px / 每版 4 张
    python scripts/review_sheet.py <出图目录> --thumb 600 --per-sheet 6

交给看图模型时，照抄这句（实测有效，能挡住"写作文"）：
    只回答四类毛病：断词 / 孤字（末行只剩 1~2 字）/ 压字出框 / 数量词对不上。
    不要写图像描述。每张一行：`card-XX: 无问题` 或 `card-XX: 现象`。
"""
import argparse
import glob
import os
import sys

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
FONT = os.path.join(ROOT, "assets", "fonts", "ZCOOLKuaiLe-Regular.ttf")


def label_font(size):
    for p in (FONT, r"C:\Windows\Fonts\arialbd.ttf"):
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def main():
    ap = argparse.ArgumentParser(description="复核用缩略图（拼版可选，更慢）")
    ap.add_argument("out_dir", help="出图目录（里面是 card-*.png）")
    ap.add_argument("--thumb", type=int, default=720, help="缩略图宽度（默认 720）")
    ap.add_argument("--sheet", action="store_true",
                    help="额外生成拼版图。⚠ 实测：一次问 4 张的调用 >600s 未返回，"
                         "单张 30~75s —— 延迟与尺寸无关，是**输出长度**把它拖长了，默认不生成")
    ap.add_argument("--per-sheet", type=int, default=4, help="拼版每张放几张（仅在 --sheet 时）")
    ap.add_argument("--quality", type=int, default=88, help="JPEG 质量（默认 88）")
    a = ap.parse_args()

    cards = sorted(glob.glob(os.path.join(a.out_dir, "card-*.png")))
    if not cards:
        sys.exit("在 %s 里没找到 card-*.png" % a.out_dir)
    tdir = os.path.join(a.out_dir, "review", "thumb")
    sdir = os.path.join(a.out_dir, "review")
    os.makedirs(tdir, exist_ok=True)

    thumbs = []
    for p in cards:
        im = Image.open(p).convert("RGB")
        w0, h0 = im.size
        im.thumbnail((a.thumb, a.thumb * 4 // 3), Image.LANCZOS)
        name = os.path.splitext(os.path.basename(p))[0]
        out = os.path.join(tdir, name + ".jpg")
        im.save(out, quality=a.quality, optimize=True)
        thumbs.append((name, Image.open(out)))
        print("  thumb %-16s %dx%d（原 %dx%d）" % (os.path.basename(out), im.size[0], im.size[1], w0, h0))

    per = max(1, a.per_sheet)
    cols = 2 if per <= 4 else 3
    tw, th = thumbs[0][1].size
    pad, bar = 16, 44
    font = label_font(30)
    sheets = []
    for si in range(0, len(thumbs), per) if a.sheet else []:
        chunk = thumbs[si:si + per]
        rows = (len(chunk) + cols - 1) // cols
        W = cols * tw + (cols + 1) * pad
        H = rows * (th + bar) + (rows + 1) * pad
        sheet = Image.new("RGB", (W, H), (245, 245, 245))
        d = ImageDraw.Draw(sheet)
        for i, (name, im) in enumerate(chunk):
            cx = pad + (i % cols) * (tw + pad)
            cy = pad + (i // cols) * (th + bar + pad)
            d.rectangle([cx, cy, cx + tw, cy + bar - 8], fill=(255, 255, 255))
            d.text((cx + 10, cy + 6), name, fill=(20, 20, 20), font=font)
            sheet.paste(im, (cx, cy + bar))
        out = os.path.join(sdir, "sheet-%02d.jpg" % (len(sheets) + 1))
        sheet.save(out, quality=a.quality, optimize=True)
        sheets.append(out)
        print("  sheet %-16s %d 张 / %dx%d / %.0f KB"
              % (os.path.basename(out), len(chunk), W, H, os.path.getsize(out) / 1024.0))

    tot_orig = sum(os.path.getsize(p) for p in cards) / 1048576.0
    tot_thumb = sum(os.path.getsize(os.path.join(tdir, n + ".jpg")) for n, _ in thumbs) / 1048576.0
    tot_sheet = sum(os.path.getsize(p) for p in sheets) / 1048576.0
    print("\n原图 %.1f MB → 缩略图 %.2f MB%s" % (tot_orig, tot_thumb,
          " / 拼版 %.2f MB" % tot_sheet if sheets else ""))
    print("优先做文字级预检：`python scripts/preflight.py <spec.json>` —— 孤字/断词/数量词"
          "三类**不需要看图**，0 秒 0 token。")
    print("真要看观感时：抽查 1~2 张 %s/card-XX.jpg 就够。实测延迟**与尺寸无关**"
          "（同一张图 300px 66s / 1440px 47s，全是服务商波动），成本看**调用次数与输出长度**："
          "一次只问一个问题、只要一行答案；别拼版、别逐张全看、改完文案不用重看。"
          % (tdir.replace("\\", "/")))


if __name__ == "__main__":
    main()