# -*- coding: utf-8 -*-
"""doctor.py —— 环境自检

在跑 build / render 之前先执行这个，它会告诉你缺什么、怎么补。
    python scripts/doctor.py
"""
import io
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

OK, WARN, BAD = "  [ok]  ", "  [warn]", "  [FAIL]"
_warn, _fail = [], []


def ok(msg):
    print(OK, msg)


def warn(msg, fix=""):
    print(WARN, msg)
    if fix:
        print("         →", fix)
    _warn.append(msg)


def fail(msg, fix=""):
    print(BAD, msg)
    if fix:
        print("         →", fix.replace("\n", "\n           "))
    _fail.append(msg)


def check_python():
    v = sys.version_info
    if v >= (3, 8):
        ok("Python %d.%d.%d" % (v[0], v[1], v[2]))
    else:
        fail("Python %d.%d 太老，需要 3.8+" % (v[0], v[1]))


def check_yaml():
    try:
        import yaml
        ok("pyyaml %s（可以读 .yaml 规格）" % getattr(yaml, "__version__", "?"))
    except ImportError:
        warn("没装 pyyaml，读不了 .yaml 规格",
             "pip install pyyaml\n"
             "或者把规格存成 .json —— build.py 也能读，且零依赖")


def check_modules():
    for m in ("ink", "decor"):
        try:
            __import__(m)
            ok("scripts/%s.py 可导入" % m)
        except Exception as e:
            fail("scripts/%s.py 导入失败：%s" % (m, e))


def check_font():
    """字体完整性：读 TTF 表目录，比对 max(offset+length) 与文件大小。

    踩过的坑：用 curl 下大字体时被 --max-time 截断，文件看着有几十 MB 其实是坏的，
    Chrome 会**静默**加载失败并回退系统字体——表现为"字体换了但没变化"。
    """
    fdir = os.path.join(ROOT, "assets", "fonts")
    ttfs = [f for f in os.listdir(fdir) if f.lower().endswith(".ttf")] \
        if os.path.isdir(fdir) else []
    if not ttfs:
        fail("assets/fonts/ 下没有 .ttf",
             "仓库自带 ZCOOLKuaiLe-Regular.ttf，检查是否被 .gitignore 误伤")
        return
    for name in sorted(ttfs):
        path = os.path.join(fdir, name)
        size = os.path.getsize(path)
        try:
            with open(path, "rb") as fh:
                magic = fh.read(4)
                if magic not in (b"\x00\x01\x00\x00", b"OTTO", b"true", b"ttcf"):
                    fail("%s 不是有效字体（magic=%r）" % (name, magic))
                    continue
                fh.seek(4)
                num = struct.unpack(">H", fh.read(2))[0]
                fh.seek(12)
                recs = fh.read(num * 16)
            need = 0
            for i in range(num):
                off, ln = struct.unpack(">II", recs[i * 16 + 8:i * 16 + 16])
                need = max(need, off + ln)
            if size >= need:
                ok("%s 完整（%.1f MB）" % (name, size / 1048576.0))
            else:
                fail("%s 被截断：文件 %.1f MB，表数据需要 %.1f MB，缺 %d 字节"
                     % (name, size / 1048576.0, need / 1048576.0, need - size),
                     "重新完整下载（注意别让 curl 的 --max-time 把它掐断）")
        except Exception as e:
            fail("%s 读取失败：%s" % (name, e))


def check_backend():
    """渲染后端预检：实测 CDP 和 CLI 哪个能出图，各花多久。

    为什么要预检：CLI 后端在受限沙箱里会因为管道被拦而**静默返回 0 字节**，
    如果等到跑 pipeline 才发现，Agent 会花大量时间去查「Chrome 是不是坏了」。
    这里 3 秒给出结论，并直接告诉 Agent 该设哪个 T2I_BACKEND。
    """
    import shutil
    import tempfile
    import time
    try:
        import ink
        import render as _r
    except Exception as e:
        fail("渲染模块导入失败：%s" % e)
        return
    tmp = tempfile.mkdtemp(prefix="t2i-doctor-")
    try:
        html = ink.render_card({"layout": "chain", "title": "doctor",
                                "steps": [{"text": "① 自检"}]},
                               0, 1, {"frame": ["pen"]},
                               _r.file_url(os.path.join(ROOT, "assets", "fonts",
                                                        "ZCOOLKuaiLe-Regular.ttf")))
        hp = os.path.join(tmp, "probe.html")
        with io.open(hp, "w", encoding="utf-8") as f:
            f.write(html)
        results = {}
        for name in ("cdp", "cli"):
            out = os.path.join(tmp, "probe-%s.png" % name)
            t0 = time.perf_counter()
            try:
                if name == "cdp":
                    import cdp
                    shot_ok, msg = cdp.shoot(hp, out, 1080, 1440, 2)
                else:
                    b = _r.find_browser() or ""
                    shot_ok, msg = _r._shoot_cli(b, hp, out, 1080, 1440, 2, 60)
            except Exception as e:                 # noqa: BLE001
                shot_ok, msg = False, str(e)[:70]
            results[name] = (shot_ok, "%s（%.1fs）" % (msg, time.perf_counter() - t0))
        good = [k for k, v in results.items() if v[0]]
        detail = " / ".join("%s %s" % (k.upper(), results[k][1]) for k in ("cdp", "cli"))
        if not good:
            fail("两个渲染后端都出不了图", "看下面的细节，通常是沙箱拦了管道或没有浏览器")
            for k in ("cdp", "cli"):
                print("         %s -> %s" % (k.upper(), results[k][1]))
        elif len(good) == 2:
            ok("渲染后端：CDP 与 CLI 都可用（%s）" % detail)
        else:
            warn("只有 %s 后端可用；建议设 T2I_BACKEND=%s" % (good[0].upper(), good[0]))
            print("         %s" % detail)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def check_browser():
    try:
        from render import find_browser
    except Exception as e:
        fail("scripts/render.py 导入失败：%s" % e)
        return
    exe = find_browser()
    if exe:
        ok("浏览器：%s" % exe)
    else:
        fail("找不到 Chrome / Chromium / Edge",
             "装一个，或用环境变量指定：\n"
             "  Windows:  set T2I_BROWSER=C:\\path\\to\\chrome.exe\n"
             "  macOS/Linux:  export T2I_BROWSER=/path/to/chrome")


def main():
    print("text-to-infographic · 环境自检")
    print("仓库：%s\n" % ROOT)
    check_python()
    check_modules()
    check_font()
    check_yaml()
    check_browser()
    check_backend()
    print()
    if _fail:
        print("有 %d 项必须修复，否则跑不起来。" % len(_fail))
        return 1
    if _warn:
        print("%d 项警告，不影响主流程。" % len(_warn))
    else:
        print("全部通过。")
    print("\n下一步：\n"
          "  python scripts/validate.py examples/json/agent-roadmap.json   # 规格门\n"
          "  python scripts/pipeline.py examples/json/agent-roadmap.json -o out/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
