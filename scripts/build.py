# -*- coding: utf-8 -*-
"""build.py —— 把 cards 规格编译成 HTML

用法
    python build.py examples/agent-handbook.yaml -o build/
    python build.py cards.json -o build/ --frame pen        # 强制指定外框
    python build.py cards.yaml -o build/ --strict           # 有文案溢出就报错退出

规格支持 YAML（需 pyyaml）和 JSON（零依赖）。规格格式见 templates/cards.example.yaml。
"""
import argparse
import io
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ink  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DEFAULT_FONT = os.path.join(ROOT, "assets", "fonts", "ZCOOLKuaiLe-Regular.ttf")


def load_spec(path):
    text = io.open(path, encoding="utf-8").read()
    if path.lower().endswith(".json"):
        return json.loads(text)
    try:
        import yaml
    except ImportError:
        raise SystemExit(
            "读 YAML 规格需要 pyyaml：\n  pip install pyyaml\n"
            "或者把规格存成 .json（JSON 零依赖）")
    return yaml.safe_load(text)


def file_url(path):
    """转成浏览器能吃的 file:/// URL。Windows 的 D:\\a\\b → file:///D:/a/b"""
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + p


def main():
    ap = argparse.ArgumentParser(description="把 cards 规格编译成 HTML")
    ap.add_argument("spec", help="规格文件（.yaml / .yml / .json）")
    ap.add_argument("-o", "--out", default="build", help="输出目录，默认 build/")
    ap.add_argument("--frame", choices=["pen", "card", "none"], default=None,
                    help="强制所有卡用同一种外框，覆盖规格里的设置")
    ap.add_argument("--font", default=DEFAULT_FONT, help="正文字体文件路径")
    ap.add_argument("--no-decor", action="store_true", help="不渲染装饰零件")
    ap.add_argument("--strict", action="store_true",
                    help="有文案溢出（被自动缩字号）就报错退出，便于 CI")
    args = ap.parse_args()

    spec = load_spec(args.spec)
    cards = spec.get("cards") or []
    if not cards:
        raise SystemExit("规格里没有 cards，检查缩进是否被 YAML 吃掉")

    meta = dict(spec.get("meta") or {})
    if args.frame:
        meta["frame"] = [args.frame]
    if args.no_decor:
        meta["decor"] = False

    font = args.font if os.path.isabs(args.font) else os.path.join(ROOT, args.font)
    if not os.path.exists(font):
        raise SystemExit("找不到字体文件：%s\n（仓库自带 assets/fonts/ZCOOLKuaiLe-Regular.ttf）" % font)

    outdir = args.out if os.path.isabs(args.out) else os.path.join(os.getcwd(), args.out)
    if not os.path.isdir(outdir):
        os.makedirs(outdir)
    else:
        # 同上：避免规格页数变少后残留旧卡片
        for f in os.listdir(outdir):
            if f.startswith("card-") and f.endswith(".html"):
                os.remove(os.path.join(outdir, f))

    for i, card in enumerate(cards):
        html = ink.render_card(card, i, len(cards), meta, file_url(font))
        name = "card-%02d.html" % (i + 1)
        with io.open(os.path.join(outdir, name), "w", encoding="utf-8") as f:
            f.write(html)
        print("built %s  [%s]  %s" % (name, card.get("layout", "bullets"),
                                      card.get("title", "")))

    print("\n共 %d 页 → %s" % (len(cards), outdir))
    if ink.WARN:
        print("\n⚠ 以下文案超出容器宽度，被自动缩小字号（建议精简或加宽）：")
        for w in ink.WARN:
            print("  -", w)
        if args.strict:
            return 1
    else:
        print("宽度自检通过，无文案溢出")
    return 0


if __name__ == "__main__":
    sys.exit(main())
