# -*- coding: utf-8 -*-
"""cdp.py —— 纯标准库的 Chrome DevTools Protocol 客户端（无第三方依赖）

为什么默认走 CDP，而不是 `--screenshot` CLI：

1. **不依赖 stdout / 管道**。CLI 的 `--dump-dom` 靠 stdout 回传结果，在受限沙箱或
   受限 shell 里会被拦（实测报 `CreatePipe permission denied`），于是拿到 0 字节。
   CDP 走 WebSocket，不受这个限制。
2. **快**。CLI 每次启动一个 Chrome 约 2.5s；CDP 复用同一个实例，约 0.8s/张，
   一次 pipeline 的十几轮测量只启一次浏览器。

⚠ 不要写「Chrome 132+ 移除了 CLI 导出 flag」这类结论——**实测不成立**：
本机 Chrome 152.0.7977.84 直接跑
`chrome.exe --headless=new --screenshot=out.png file:///...`
输出 `131821 bytes written to file ...`，完全正常。CLI 没坏，只是在这类环境下
更容易被拦、也更慢。所以 CLI 保留为兜底（`T2I_BACKEND=cli` 可强制）。

对外的三个函数（measure.py / render.py 只认这三个）：
    eval_on_page(html_path, expr)        -> dict   等字体加载完再求值 JS 表达式
    shoot(html_path, png, w, h, scale)   -> (ok, msg)
    reset()                                         关掉缓存的浏览器实例
"""
import atexit
import base64
import json
import os
import socket
import struct
import subprocess
import sys
import tempfile
import time
from urllib.request import urlopen

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


# ───────────────────────────── 极简 WebSocket 客户端 ─────────────────────────────
class _WS(object):
    """够用的 RFC6455 客户端：文本帧、客户端掩码、支持分片与大帧。"""

    def __init__(self, host, port, path, timeout=120):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        key = base64.b64encode(os.urandom(16)).decode()
        req = ("GET %s HTTP/1.1\r\nHost: %s:%d\r\nUpgrade: websocket\r\n"
               "Connection: Upgrade\r\nSec-WebSocket-Key: %s\r\n"
               "Sec-WebSocket-Version: 13\r\n\r\n" % (path, host, port, key))
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise IOError("websocket handshake closed")
            buf += chunk
        head, rest = buf.split(b"\r\n\r\n", 1)
        if b"101" not in head.split(b"\r\n", 1)[0]:
            raise IOError("websocket handshake failed: %s" % head.split(b"\r\n", 1)[0])
        self._buf = rest

    def _exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise IOError("websocket closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def send(self, text):
        data = text.encode("utf-8")
        n = len(data)
        head = bytearray([0x81])                     # FIN + text
        mask = os.urandom(4)
        if n < 126:
            head.append(0x80 | n)
        elif n < 65536:
            head.append(0x80 | 126); head += struct.pack(">H", n)
        else:
            head.append(0x80 | 127); head += struct.pack(">Q", n)
        head += mask
        self.sock.sendall(bytes(head) + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        """返回一条完整消息（自动拼分片，忽略 ping/close 之外的杂帧）。"""
        acc = None
        while True:
            b0, b1 = self._exact(2)
            fin, op = b0 & 0x80, b0 & 0x0F
            ln = b1 & 0x7F
            if ln == 126:
                ln = struct.unpack(">H", self._exact(2))[0]
            elif ln == 127:
                ln = struct.unpack(">Q", self._exact(8))[0]
            if b1 & 0x80:                            # 服务端不该掩码，遇到就解
                m = self._exact(4)
            else:
                m = None
            payload = self._exact(ln) if ln else b""
            if m:
                payload = bytes(b ^ m[i % 4] for i, b in enumerate(payload))
            if op == 0x8:                            # close
                raise IOError("websocket closed by peer")
            if op == 0x9:                            # ping -> pong
                continue
            if op == 0xA:
                continue
            if acc is None:
                acc = bytearray(payload)
                if fin:
                    return bytes(acc).decode("utf-8", "replace")
            else:
                acc += payload
                if fin:
                    return bytes(acc).decode("utf-8", "replace")


# ───────────────────────────────── CDP 会话 ─────────────────────────────────
class CDP(object):
    """一个 headless Chrome + 一个 page target，够 build/measure/render 用。"""

    def __init__(self, browser_path):
        self.exe = browser_path
        self.prof = os.path.abspath(tempfile.mkdtemp(prefix="t2i-cdp-"))
        self.proc = subprocess.Popen(
            [self.exe, "--headless=new", "--disable-gpu", "--no-sandbox",
             "--no-first-run", "--disable-http-cache", "--disk-cache-size=1",
             "--allow-file-access-from-files", "--hide-scrollbars",
             "--remote-debugging-port=0", "--user-data-dir=%s" % self.prof,
             "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port, path = self._wait_port()
        self.ws = _WS("127.0.0.1", port, path)
        self._id = 0
        self.session = None
        self._cmd("Target.setDiscoverTargets", {"discover": False})
        tid = self._cmd("Target.createTarget", {"url": "about:blank"})["targetId"]
        self.session = self._cmd("Target.attachToTarget",
                                 {"targetId": tid, "flatten": True})["sessionId"]
        self._cmd("Page.enable")
        self._cmd("Runtime.enable")

    # ---- 底层 ----
    def _wait_port(self, timeout=25):
        marker = os.path.join(self.prof, "DevToolsActivePort")
        deadline = time.time() + timeout
        while time.time() < deadline:
            if os.path.exists(marker):
                try:
                    with open(marker, "r") as f:
                        lines = f.read().split()
                    if lines:
                        return int(lines[0]), (lines[1] if len(lines) > 1
                                               else "/devtools/browser")
                except (ValueError, IOError):
                    pass
            time.sleep(0.15)
        raise RuntimeError("headless Chrome 没起来（DevToolsActivePort 超时未生成）")

    def _cmd(self, method, params=None, timeout=120):
        self._id += 1
        mid = self._id
        msg = {"id": mid, "method": method, "params": params or {}}
        if self.session:
            msg["sessionId"] = self.session
        self.ws.send(json.dumps(msg))
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.ws.recv()
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if obj.get("id") != mid:
                if "error" in obj and obj.get("id") is None:
                    continue
                continue
            if "error" in obj:
                raise RuntimeError("%s → %s" % (method, obj["error"].get("message")))
            return obj.get("result", {})
        raise RuntimeError("%s 超时" % method)

    def evaljs(self, expression, await_promise=False, timeout=120):
        r = self._cmd("Runtime.evaluate", {
            "expression": expression, "returnByValue": True,
            "awaitPromise": await_promise, "userGesture": True}, timeout=timeout)
        if r.get("exceptionDetails"):
            raise RuntimeError("页面 JS 异常：%s" % json.dumps(
                r["exceptionDetails"].get("exception", {}).get("description", ""))[:300])
        return r.get("result", {}).get("value")

    def goto(self, url, timeout=60):
        self._cmd("Page.navigate", {"url": url}, timeout=timeout)
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.evaljs("document.readyState") in ("complete", "interactive"):
                break
            time.sleep(0.1)
        # 字体没加载完就量宽度 = 量了个假的
        try:
            self.evaljs("document.fonts.ready.then(function(){return 1})",
                        await_promise=True, timeout=timeout)
        except RuntimeError:
            pass
        self.evaljs("document.fonts ? document.fonts.load('44px ZCOOL') && 1 : 1",
                    await_promise=True, timeout=30)
        time.sleep(0.05)

    def metrics(self, width, height, scale):
        self._cmd("Emulation.setDeviceMetricsOverride", {
            "width": int(width), "height": int(height),
            "deviceScaleFactor": scale, "mobile": False})

    def page_setup(self, html_path, width, height, scale):
        self.goto(file_url(html_path))
        self.metrics(width, height, scale)

    def screenshot(self, width, height, scale):
        r = self._cmd("Page.captureScreenshot", {
            "format": "png", "captureBeyondViewport": False,
            "clip": {"x": 0, "y": 0, "width": int(width),
                     "height": int(height), "scale": 1}})
        return base64.b64decode(r["data"])

    def close(self):
        try:
            self._cmd("Browser.close", timeout=10)
        except Exception:
            pass
        try:
            self.ws.sock.close()
        except Exception:
            pass
        try:
            if self.proc.poll() is None:
                self.proc.terminate()
        except Exception:
            pass
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(self.proc.pid)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        import shutil
        shutil.rmtree(self.prof, ignore_errors=True)


def file_url(path):
    p = os.path.abspath(path).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    return "file://" + p


# ───────────────────────────── 进程内复用的实例 ─────────────────────────────
_INST = None
_BROKEN = False          # 起不来一次就不再反复尝试，调用方回落到 CLI 路径


def browser_or_none():
    global _INST, _BROKEN
    if _BROKEN:
        return None
    if _INST is not None:
        return _INST
    try:
        import render
        exe = render.find_browser()
        if not exe:
            _BROKEN = True
            return None
        _INST = CDP(exe)
        atexit.register(shutdown)
        return _INST
    except Exception as e:                     # noqa: BLE001
        sys.stderr.write("  [cdp] 起不来，回落到 CLI：%s\n" % e)
        _BROKEN = True
        return None


def shutdown():
    global _INST
    if _INST is not None:
        inst, _INST = _INST, None
        try:
            inst.close()
        except Exception:
            pass


def reset():
    shutdown()
    global _BROKEN
    _BROKEN = False


def eval_on_page(html_path, expression, width=1080, height=1440, scale=1):
    """在真实浏览器里跑一段 JS 表达式，返回它的值（通常是 dict）。"""
    b = browser_or_none()
    if b is None:
        raise RuntimeError("CDP 后端不可用")
    b.page_setup(html_path, width, height, scale)
    return b.evaljs(expression, await_promise=False, timeout=120)


def shoot(html_path, png_path, width, height, scale):
    """截一屏，返回 (ok, 摘要)。"""
    b = browser_or_none()
    if b is None:
        return False, "CDP 后端不可用"
    try:
        b.page_setup(html_path, width, height, scale)
        data = b.screenshot(width, height, scale)
        with open(png_path, "wb") as f:
            f.write(data)
        return True, "%d bytes (cdp)" % len(data)
    except Exception as e:                     # noqa: BLE001
        return False, "CDP 截图失败：%s" % e


if __name__ == "__main__":
    # 自检：python cdp.py <某个.html>
    import ink
    p = sys.argv[1] if len(sys.argv) > 1 else None
    W, H = ink.W_CARD + ink.MARGIN * 2, ink.H_CARD + ink.MARGIN * 2
    if p:
        print("measure:", json.dumps(
            eval_on_page(p, "(function(){var s=document.querySelector('.stage');"
                            "return {w:s?s.viewBox.baseVal.width:0,h:s?s.viewBox"
                            ".baseVal.height:0,t:document.querySelectorAll('text')"
                            ".length,f:(document.fonts?document.fonts.size:0)};})()"),
            ensure_ascii=False))
    out = os.path.join(tempfile.gettempdir(), "t2i-cdp-selftest.png")
    if p:
        print("shoot:", shoot(p, out, W, H, 2))
