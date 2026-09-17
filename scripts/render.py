# -*- coding: utf-8 -*-
"""render.py —— 把 HTML 批量截成 PNG（跨平台，只用标准库）

用法
    python render.py build/ -o out/              # 渲染 build/ 下所有 card-*.html
    python render.py build/ -o out/ --scale 2    # 2 倍图（默认）
    python render.py build/ --browser /path/to/chrome

为什么不用 Playwright：Chrome/Edge 自带的 `--headless --screenshot` 就够，
少一个几百 MB 的依赖。

两个必须知道的坑（都是实测踩出来的）
  1. Chromium 系的 `--screenshot` **必须收到本机原生路径**。在 Windows 上传
     POSIX 风格的 `/c/Users/...` 会报 "系统找不到指定的路径" 并且**静默不产出**，
     连报错都不明显。所以这里一律用 os.path.abspath() 的返回值。
  2. **每次都要用全新的 --user-data-dir**。Chrome 会把 file:// 页面缓存进 profile，
     复用同一目录会出现「HTML 改了但截图没变」的假象。
"""
import argparse
import glob
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ink  # noqa: E402

WINDOWS_CANDIDATES = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
]
MAC_CANDIDATES = [
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
]
LINUX_NAMES = ["google-chrome", "google-chrome-stable", "chromium",
               "chromium-browser", "microsoft-edge", "microsoft-edge-stable",
               "brave-browser"]


def find_browser(explicit=None):
    """按 环境变量 → 显式指定 → 平台默认路径 的顺序找一个 Chromium 系浏览器。"""
    for cand in (os.environ.get("T2I_BROWSER"), explicit):
        if cand and os.path.exists(cand):
            return cand
    if sys.platform.startswith("win"):
        candidates = WINDOWS_CANDIDATES
    elif sys.platform == "darwin":
        candidates = MAC_CANDIDATES
    else:
        candidates = []
    for c in candidates:
        if c and os.path.exists(c):
            return c
    for name in LINUX_NAMES:
        p = shutil.which(name)
        if p:
            return p
    return None


def file_url(path):
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + p


def shoot(browser, html_path, png_path, width, height, scale, timeout=120):
    """截一张图。返回 (ok, 输出摘要)。默认 CDP 优先、CLI 兜底。

    为什么默认 CDP：不依赖 stdout（受限沙箱会拦 CreatePipe）且快 3 倍
    （复用浏览器实例）。**CLI 本身没坏**——本机 Chrome 152 实测
    `--screenshot` 正常写出文件，所以它是有价值的兜底。
    用环境变量 T2I_BACKEND=cdp|cli|auto 强制指定后端。
    """
    import os as _os
    backend = (_os.environ.get("T2I_BACKEND") or "auto").lower()
    if backend == "cli":
        return _shoot_cli(browser, html_path, png_path, width, height, scale, timeout)
    why_cdp = ""
    if backend in ("auto", "cdp"):
        try:
            import cdp
            ok, msg = cdp.shoot(html_path, png_path, width, height, scale)
            if ok:
                return True, msg
            why_cdp = msg
        except Exception as e:                   # noqa: BLE001
            why_cdp = "CDP 不可用：%s" % e
    ok, msg = _shoot_cli(browser, html_path, png_path, width, height, scale, timeout)
    return ok, (msg if ok else "%s（CDP：%s）" % (msg, why_cdp))


def _shoot_cli(browser, html_path, png_path, width, height, scale, timeout=120):
    """老路子：`--headless=new --screenshot=`。"""
    prof = tempfile.mkdtemp(prefix="t2i-prof-")
    cmd = [
        browser,
        "--headless=new", "--disable-gpu", "--hide-scrollbars", "--no-first-run",
        "--allow-file-access-from-files",
        "--disable-http-cache", "--disk-cache-size=1",      # 坑 2：别让 profile 缓存住页面
        "--user-data-dir=%s" % os.path.abspath(prof),
        "--force-device-scale-factor=%d" % scale,
        "--window-size=%d,%d" % (width * scale // scale, height),
        "--virtual-time-budget=4000",
        "--screenshot=%s" % os.path.abspath(png_path),      # 坑 1：必须是原生路径
        file_url(html_path),
    ]
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           timeout=timeout)
        out = (r.stdout or b"").decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        out = "timeout after %ds" % timeout
    finally:
        shutil.rmtree(prof, ignore_errors=True)
    ok = os.path.exists(png_path) and os.path.getsize(png_path) > 0
    if not ok:
        for line in out.splitlines():
            if "Failed" in line or "error" in line.lower():
                return False, line.strip()
        return False, (out.strip().splitlines() or ["no output"])[-1]
    return True, "%d bytes" % os.path.getsize(png_path)


def main():
    ap = argparse.ArgumentParser(description="把 HTML 批量截成 PNG")
    ap.add_argument("html_dir", help="存放 card-*.html 的目录")
    ap.add_argument("-o", "--out", default=None, help="PNG 输出目录，默认与 html_dir 相同")
    ap.add_argument("--scale", type=int, default=2, help="设备像素比，默认 2（即 2 倍图）")
    ap.add_argument("--width", type=int, default=ink.W_CARD + ink.MARGIN * 2)
    ap.add_argument("--height", type=int, default=ink.H_CARD + ink.MARGIN * 2)
    ap.add_argument("--browser", default=None, help="手动指定浏览器可执行文件")
    args = ap.parse_args()

    browser = find_browser(args.browser)
    if not browser:
        raise SystemExit(
            "找不到 Chrome / Chromium / Edge。\n"
            "装一个，或者用环境变量指定：\n"
            "  set T2I_BROWSER=C:\\path\\to\\chrome.exe   (Windows)\n"
            "  export T2I_BROWSER=/path/to/chrome         (macOS / Linux)\n"
            "也可以用 --browser 参数。")

    html_dir = os.path.abspath(args.html_dir)
    out_dir = os.path.abspath(args.out or args.html_dir)
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)

    files = sorted(glob.glob(os.path.join(html_dir, "card-*.html")))
    if not files:
        raise SystemExit("%s 下没找到 card-*.html，先跑 build.py" % html_dir)

    print("浏览器：%s" % browser)
    print("渲染 %d 页 @%dx，画布 %d×%d\n" % (len(files), args.scale, args.width, args.height))
    failed = []
    for f in files:
        png = os.path.join(out_dir, os.path.splitext(os.path.basename(f))[0] + ".png")
        ok, msg = shoot(browser, f, png, args.width, args.height, args.scale)
        print("  %-16s %s" % (os.path.basename(png), msg))
        if not ok:
            failed.append((png, msg))

    if failed:
        print("\n%d 页渲染失败：" % len(failed))
        for p, m in failed:
            print("  %s  ← %s" % (p, m))
        return 1
    print("\n全部完成 → %s" % out_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
