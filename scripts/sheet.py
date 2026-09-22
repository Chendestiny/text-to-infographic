# -*- coding: utf-8 -*-
"""sheet.py —— 拼版图：把 N 张竖版卡片拼成一张带标题/角标的联系表。

为什么要有它（而不是继续在 README 里一行放两张缩略图）：
  · **一次看全**。15 个版式 / N 套皮肤散成十几张图时，人只会看前两张；
    拼成一张才真的"一眼比出画歪的那张"。
  · **README 只有一张图**，不再是一行行的图片表格（那玩意儿在手机上会把
    页面撑成一条瀑布，而且每个 `<img>` 都是一次请求）。
  · 顺带当回归证据：拼版跑不出来（少图 / 顺序乱）本身就是一个信号。

约定
  · 每格 = 一张 3:4 竖图的等比缩略图 + 一条白底角标
  · 卡片底色是深色的皮肤（终端/蓝图/北欧）在浅灰画布上会自带描边感，不用额外加框
  · 字体优先用仓库自带的站酷快乐体（能显示中文，且不依赖系统字体）
"""
import os

FONT_CANDIDATES = (
    os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                 "assets", "fonts", "ZCOOLKuaiLe-Regular.ttf"),
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\arialbd.ttf",
)


def label_font(size):
    from PIL import ImageFont
    for p in FONT_CANDIDATES:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except OSError:
                pass
    return ImageFont.load_default()


def contact_sheet(pngs, out, cols=4, thumb_w=420, title="", note="",
                  bg=(238, 238, 236), label_size=22, title_size=40, labels=None):
    """把 `pngs` 拼成一张联系表并保存到 `out`。返回 out；没有输入则返回 None。

    pngs: 图片路径列表（顺序 = 阅读顺序）
    cols: 每行几格
    title/note: 顶部大标题 + **右对齐**的小注（左对齐会和标题叠在一起，踩过）
    labels: 每格角标文字（不给就用文件名，文件名带一堆前缀时很难看）
    """
    from PIL import Image, ImageDraw
    ims = []
    for i, p in enumerate(pngs):
        im = Image.open(p).convert("RGB")
        im.thumbnail((thumb_w, thumb_w * 4 // 3), Image.LANCZOS)
        name = (labels[i] if labels and i < len(labels)
                else os.path.splitext(os.path.basename(p))[0])
        ims.append((name, im))
    if not ims:
        return None
    tw, th = ims[0][1].size
    rows = (len(ims) + cols - 1) // cols
    pad = 18
    # 角标支持多行（`\n` 分行）：一行标题 + 一行说明，比截断强得多
    nlines = max([name.count("\n") + 1 for name, _ in ims] or [1])
    bar = 34 + 30 * nlines
    head = 96 if (title or note) else 0
    W = cols * tw + (cols + 1) * pad
    H = head + rows * (th + bar) + (rows + 1) * pad
    sheet = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(sheet)
    if title:
        d.text((pad + 6, pad + 14), title, fill=(14, 14, 14), font=label_font(title_size))
    if note:
        nf = label_font(label_size + 4)
        w = d.textlength(note, font=nf)
        d.text((W - pad - w - 8, pad + 32), note, fill=(124, 124, 124), font=nf)
    f = label_font(label_size)
    fs = label_font(label_size - 6)
    for i, (name, im) in enumerate(ims):
        cx = pad + (i % cols) * (tw + pad)
        cy = head + pad + (i // cols) * (th + bar + pad)
        d.rectangle([cx, cy, cx + tw, cy + bar - 8], fill=(255, 255, 255))
        lines = name.split("\n")
        for k, ln in enumerate(lines):
            # ★ 角标必须**按格宽截断**：`13 cover_title · 大字标题封面` 这类长名字
            #   会直接压到下一格里（实测被裁成半个字）
            while ln and d.textlength(ln, font=(f if k == 0 else fs)) > tw - 24:
                ln = ln[:-1]
            d.text((cx + 12, cy + 8 + k * 30), ln, fill=(24, 24, 24) if k == 0 else (110, 110, 110),
                   font=(f if k == 0 else fs))
        sheet.paste(im, (cx + (tw - im.size[0]) // 2, cy + bar))
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    sheet.save(out, optimize=True)
    return out
