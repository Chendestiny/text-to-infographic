# -*- coding: utf-8 -*-
"""measure.py —— 用真实浏览器测量 HTML 的溢出（编排流的 measure 节点）

为什么不用 ink.tw() 估算：字体度量估不准（拉丁宽、bold、letter-spacing 全是变量），
估算错了就会出现「build 报没问题、图上文字出框」。这里直接让 Chrome 渲染，
用 getBBox() 拿每个 <text> 的真实包围盒，再和 build 时埋进 HTML 的方框清单比对。

用法
    from measure import measure, analyze
    rep = measure(html_path)          # 真实测量
    issues = analyze(rep, boxes)      # 出溢出清单

输出结构
    rep = {
      "stage": {w, h},                # SVG 画布
      "svg":  [{s, x, y, w, h}],      # 每个 <text> 的真实 bbox（文档序）
      "html": [{s, w, sw, cw, h}],    # .row 的宽/scrollWidth
      "card": {w, h, sh},             # 卡片容器
      "text": "...",                  # 卡片全部可见文字（内容门用）
      "fit":  {rowBottom, limit, n}   # HTML 行的纵向拟合
    }
"""
import io
import sys
import json
import os
import re
import subprocess
import tempfile

MEASURE_FN = """(function(){
  var rep = {svg: [], html: [], stage: null, card: null};
  var stage = document.querySelector('.stage');
  if (stage) {
    var vb = stage.viewBox.baseVal;
    rep.stage = {w: vb.width, h: vb.height};
    var ts = stage.querySelectorAll('text');
    for (var i = 0; i < ts.length; i++) {
      var b = ts[i].getBBox();
      rep.svg.push({s: (ts[i].textContent||'').slice(0,44),
                    x: +b.x.toFixed(1), y: +b.y.toFixed(1),
                    w: +b.width.toFixed(1), h: +b.height.toFixed(1)});
    }
  }
  var rows = document.querySelectorAll('.row');
  for (var j = 0; j < rows.length; j++) {
    var r = rows[j], b = r.getBoundingClientRect();
    rep.html.push({s: (r.innerText||'').slice(0,44), w: +b.width.toFixed(1),
                   sw: r.scrollWidth, cw: r.clientWidth, h: +b.height.toFixed(1)});
  }
  var card = document.querySelector('.card');
  if (card) { var cb = card.getBoundingClientRect();
    rep.card = {w: +cb.width.toFixed(1), h: +cb.height.toFixed(1),
                sh: card.scrollHeight};
    /* 内容门用：卡片里所有可见文字（含 SVG <text>）。规格里登记过的每一段文字
       都必须在这里找到 —— 几何检查抓不到「字被吞掉」，因为图上压根没那行字。 */
    rep.text = card.textContent || '';
    /* 纵向体检：bullets 这类 HTML 行版式的行高由内容撑开（一行 desc ≈ 57px，
       加上 head 与 padding，单行就有 200px），SVG 的宽度检查完全管不到它。
       卡片自带 padding，内容真正的底边上限 = card.bottom - paddingTop。 */
    var rr = document.querySelectorAll('.row');
    var last = rr.length ? rr[rr.length-1].getBoundingClientRect() : null;
    rep.fit = {rowBottom: last ? +last.bottom.toFixed(1) : 0,
               cardBottom: +cb.bottom.toFixed(1),
               limit: +(cb.bottom - (parseFloat(getComputedStyle(card).paddingTop)||0)).toFixed(1),
               n: rr.length}; }
  return rep;
})()"""

MEASURE_JS = ("\n<script>\nwindow.__t2i = " + MEASURE_FN +
              ";\ndocument.title = 'T2I' + JSON.stringify(window.__t2i);\n"
              "</script>\n")

# 卡片视口：量宽度必须和真正出图时用的是同一个尺寸，否则 .row 的
# scrollWidth / clientWidth 就不是那几个 PNG 里的那几个值。
VIEWPORT = (1080, 1440)


def find_browser(explicit=None):
    """复用 render.py 的浏览器探测。"""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    from render import find_browser as fb
    return fb(explicit)


_CLI_WORKS = None          # None=没试过，True/False=结果（一次定终身，别每页都撞墙）


def _measure_cli(html_path, browser, tmp):
    """老路子：`--dump-dom` 把注入后的 DOM 打回来，从 <title> 里取报告。

    Chrome ≥132 在 Windows 上会**静默返回 0 字节**（启动器进程把浏览器分离了，
    stdout 句柄丢了），所以这里任何异常都只当成「这条路不通」。
    """
    src = io.open(html_path, encoding="utf-8").read()
    hp = os.path.join(tmp, "m.html")
    io.open(hp, "w", encoding="utf-8").write(src.replace("</body>", MEASURE_JS + "</body>"))
    p = os.path.abspath(hp).replace("\\", "/")
    if not p.startswith("/"):
        p = "/" + p
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run",
           "--allow-file-access-from-files", "--disable-http-cache",
           "--user-data-dir=%s" % os.path.join(tmp, "prof"),
           "--window-size=%d,%d" % VIEWPORT, "--virtual-time-budget=6000",
           "--dump-dom", "file://" + p]
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           timeout=120)
    except Exception:                        # noqa: BLE001
        return None
    out = (r.stdout or b"").decode("utf-8", "replace")
    m = re.search(r"<title>T2I(\{.*\})</title>", out, re.S)
    if not m:
        return None
    return json.loads(m.group(1).replace('\\"', '"'))


def measure(html_path, browser=None):
    """渲染一次 HTML，返回真实测量报告（dict）。CDP 优先，CLI 兜底。"""
    global _CLI_WORKS
    import cdp
    try:
        rep = cdp.eval_on_page(html_path, MEASURE_FN,
                               width=VIEWPORT[0], height=VIEWPORT[1])
        if rep:
            return rep
    except Exception as e:                   # noqa: BLE001
        sys.stderr.write("  [cdp] 测量不可用（%s），回落到 --dump-dom\n" % e)
    browser = browser or find_browser()
    if not browser:
        raise RuntimeError("没有可用的测量后端：CDP 起不来，也找不到浏览器")
    if _CLI_WORKS is False:
        raise RuntimeError("测量失败：CDP 与 --dump-dom 都没有返回报告（%s）" % html_path)
    tmp = tempfile.mkdtemp(prefix="t2i-m-")
    try:
        rep = _measure_cli(html_path, browser, tmp)
    finally:
        import shutil
        shutil.rmtree(tmp, ignore_errors=True)
    if rep is None:
        _CLI_WORKS = False
        raise RuntimeError("测量失败：浏览器没有返回报告（%s）" % html_path)
    _CLI_WORKS = True
    return rep


def _boxes_of(html_path):
    """从 HTML 里取出 build 时埋下的方框清单（<!--T2I_BOXES:[...]-->）。"""
    src = io.open(html_path, encoding="utf-8").read()
    m = re.search(r"<!--T2I_BOXES:(\[.*?\])-->", src, re.S)
    return json.loads(m.group(1)) if m else []


def _texts_of(html_path):
    """从 HTML 里取出 build 时埋下的文字清单（<!--T2I_TEXTS:[...]-->）。

    用非贪婪到 `-->` 为止，而不是到第一个 `]`：文字里本来就可能出现方括号。
    """
    src = io.open(html_path, encoding="utf-8").read()
    m = re.search(r"<!--T2I_TEXTS:(.*?)-->", src, re.S)
    return json.loads(m.group(1)) if m else []


def analyze(rep, boxes=None, texts=None):
    """把测量结果变成溢出清单。

    五类问题：
      missing-text   规格里登记的文字没有出现在图上（引擎吞字，几何检查抓不到）
      out-of-canvas  文本超出 SVG 画布（会被 overflow:hidden 静默裁掉）
      box-overflow   文本超出它所在的方框（画布内看得见，但压框了）
      html-overflow  HTML 行横向溢出（scrollWidth > clientWidth）
      v-overflow     HTML 行整体撑破卡片底边
    """
    issues = []
    # ★ 内容门：build 时登记过（= 规格里写了）的文字，必须真的出现在卡片上。
    # 为什么必须先查它：文字被静默吞掉时（_inline 漏了尾巴、整条副标题变空），
    # 图上没有那行字，所以既不溢出也不压框 —— 另外几道门永远发现不了。
    seen = re.sub(r"\s+", "", rep.get("text") or "")
    if texts and seen:
        for t in texts:
            if t not in seen:
                issues.append({"kind": "missing-text", "text": t[:44],
                               "note": "规格里有、图上没有（引擎吞字）"})
    st = rep.get("stage") or {"w": 824, "h": 900}
    W, H = st["w"], st["h"]
    for ti, t in enumerate(rep.get("svg", [])):
        cx, cy = t["x"] + t["w"] / 2.0, t["y"] + t["h"] / 2.0
        if t["x"] < -2 or t["x"] + t["w"] > W + 2:
            issues.append({"idx": ti, "kind": "out-of-canvas", "where": "x", "text": t["s"],
                           "real_w": t["w"], "x": t["x"], "y": t["y"],
                           "cx": cx, "cy": cy, "size": None})
        if t["y"] + t["h"] > H + 2:
            issues.append({"idx": ti, "kind": "out-of-canvas", "where": "y", "text": t["s"],
                           "y_bottom": t["y"] + t["h"], "cx": cx, "cy": cy})
        if boxes:
            hit = [b for b in boxes
                   if b["x"] - 4 <= cx <= b["x"] + b["w"] + 4
                   and b["y"] - 4 <= cy <= b["y"] + b["h"] + 4]
            if hit:
                box = min(hit, key=lambda b: b["w"] * b["h"])
                if t["w"] > box["w"] - 12:
                    issues.append({"idx": ti, "kind": "box-overflow", "text": t["s"],
                                   "real_w": t["w"], "box_w": box["w"],
                                   "box_x": box["x"], "box_y": box["y"],
                                   "cx": cx, "cy": cy, "size": None})
    for h in rep.get("html", []):
        if h["sw"] > h["cw"] + 2:
            issues.append({"kind": "html-overflow", "text": h["s"],
                           "sw": h["sw"], "cw": h["cw"]})
    # 纵向：HTML 行整体撑破卡片底边（脚本修不了，只能让 Agent 减条数或缩文案）
    fit = rep.get("fit") or {}
    if fit.get("n") and fit.get("rowBottom") and fit["rowBottom"] > fit.get("limit", 1e9) + 4:
        issues.append({"kind": "v-overflow",
                       "text": "%d 行 HTML 行撑破卡片：底边 %.0f > 上限 %.0f（多 %.0f px）"
                               % (fit["n"], fit["rowBottom"], fit["limit"],
                                  fit["rowBottom"] - fit["limit"]),
                       "row_bottom": fit["rowBottom"], "limit": fit["limit"]})
    return issues


def measure_and_analyze(html_path, browser=None):
    html_path = os.path.abspath(html_path)
    rep = measure(html_path, browser)
    return rep, analyze(rep, _boxes_of(html_path), _texts_of(html_path))
