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
  var rep = {svg: [], html: [], ink: [], slots: [], stage: null, card: null};
  var stage = document.querySelector('.stage');
  if (stage) {
    var vb = stage.viewBox.baseVal;
    rep.stage = {w: vb.width, h: vb.height};
    var ts = stage.querySelectorAll('text');
    var srect = stage.getBoundingClientRect();
    var scl = srect.width > 0 ? (vb.width / srect.width) : 1;   // 显示尺寸 → viewBox 比例
    for (var i = 0; i < ts.length; i++) {
      var b = ts[i].getBBox();
      var r = ts[i].getBoundingClientRect();
      rep.svg.push({s: (ts[i].textContent||'').slice(0,44),
                    tag: ts[i].getAttribute('data-tag') || '?',
                    /* bbox：元素自己用户空间 —— 宽度用；父级 transform 它不管 */
                    x: +b.x.toFixed(1), y: +b.y.toFixed(1),
                    w: +b.width.toFixed(1), h: +b.height.toFixed(1),
                    /* 视觉 rect：含所有 transform，已归一化到 viewBox 坐标 —— 位置用 */
                    vx: +((r.left - srect.left) * scl).toFixed(1),
                    vy: +((r.top - srect.top) * scl).toFixed(1),
                    vw: +(r.width * scl).toFixed(1),
                    vh: +(r.height * scl).toFixed(1)});
    }
  }
  /* 墨迹：方框 / 箭头 / 外框的真实 rect。
     用户在理上的判断：几何判断是 JS 的活 —— 别拿 Python 侧的名义坐标去和
     DOM 量出来的文字比，两个坐标系不同源，而且手绘笔锋会 overshoot 1~7px。 */
  rep.ink = [];
  function pushInk(el, kind) {
    try {
      var b = el.getBBox();
      if (b && b.width > 0 && b.height > 0) {
        rep.ink.push({kind: kind, x: +b.x.toFixed(1), y: +b.y.toFixed(1),
                      w: +b.width.toFixed(1), h: +b.height.toFixed(1)});
      }
    } catch (e) { /* 少数元素没有 getBBox，跳过 */ }
  }
  var iks = stage ? stage.querySelectorAll('[data-ink]') : [];
  for (var k = 0; k < iks.length; k++) {
    pushInk(iks[k], iks[k].getAttribute('data-ink') || 'box');
  }
  var fr = document.querySelector('.frame');
  if (fr) { pushInk(fr, 'frame'); }
  /* DOM 文字槽：真实渲染坐标 + 是否溢出（scrollHeight/clientHeight）
     —— DOM 模式下这就是"文字放不下"的权威判据，不用估算宽度。 */
  rep.slots = [];
  var wraps = document.querySelector('.stagewrap') || stage;
  var wr0 = wraps ? wraps.getBoundingClientRect() : null;
  var slots = document.querySelectorAll('.slots .s');
  for (var si = 0; si < slots.length; si++) {
    var el = slots[si], tr = el.getBoundingClientRect();
    var t = el.querySelector('.t');
    var cs = t ? getComputedStyle(t) : null;
    var over = false, slotH = 0, slotW = 0;
    if (t) {
      var clamp = t.style.webkitLineClamp;
      t.style.webkitLineClamp = 'unset';                 /* 先解除截断才能量到真实高度 */
      /* ★ 与**槽盒子**比，不是与文字自己比（后者两个值永远相等 → 测不到溢出） */
      over = (t.scrollHeight > el.clientHeight + 1) || (t.scrollWidth > el.clientWidth + 1);
      t.style.webkitLineClamp = clamp;
      slotH = el.clientHeight; slotW = el.clientWidth;
    }
    /* 行盒：DOM 模式下折行是浏览器做的，孤字要用**真实行盒**判（Python 侧估不准）。
       ★ `.t` 是 display:-webkit-box，Range.getClientRects() 对它返回空 →
         必须临时切回 display:block 才量得到（折行行为不变），量完还原。 */
    var lines = 0, lastW = 0;
    if (t && !over) {
      var disp = t.style.display;
      t.style.display = 'block';
      var rng = document.createRange();
      rng.selectNodeContents(t);
      var rects = rng.getClientRects();
      if (rects && rects.length) {
        lines = rects.length;
        lastW = rects[rects.length - 1].width;
      }
      t.style.display = disp;
    }
    rep.slots.push({
      left: wr0 ? +(tr.left - wr0.left).toFixed(1) : 0,
      top: wr0 ? +(tr.top - wr0.top).toFixed(1) : 0,
      w: +tr.width.toFixed(1), h: +tr.height.toFixed(1),
      text: t ? (t.textContent || '').slice(0, 30) : '',
      fs: cs ? parseFloat(cs.fontSize) : 0,
      sh: t ? t.scrollHeight : 0, ch: slotH, sw: t ? t.scrollWidth : 0,
      lines: lines, lastW: +lastW.toFixed(1),
      over: over
    });
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


def _ink_of(html_path):
    """从 HTML 里取出 build 时埋下的墨迹清单（<!--T2I_INK:[...]-->）。

    kind: box 手绘方框 / line 箭头连线 / frame 卡片外框。
    这些是文字**不该穿过**的东西 —— 拿它们的 rect 和文字 rect 求交，
    就能不启视觉模型查出"压字 / 压线 / 压框"。
    """
    try:
        src = io.open(html_path, encoding="utf-8").read()
        m = re.search(r"<!--T2I_INK:(.*?)-->", src, re.S)
        return json.loads(m.group(1)) if m else []
    except (IOError, ValueError):
        return []


def _overlap(a, b):
    """两个 rect 的交集面积（a/b 为 (x, y, w, h)）。"""
    ox = min(a[0] + a[2], b["x"] + b["w"]) - max(a[0], b["x"])
    oy = min(a[1] + a[3], b["y"] + b["h"]) - max(a[1], b["y"])
    return ox * oy if ox > 0 and oy > 0 else 0.0


def analyze(rep, boxes=None, texts=None, ink=None):
    """把测量结果变成溢出清单。

    五类问题：
      missing-text   规格里登记的文字没有出现在图上（引擎吞字，几何检查抓不到）
      out-of-canvas  文本超出 SVG 画布（会被 overflow:hidden 静默裁掉）
      box-overflow   文本超出它所在的方框（画布内看得见，但压框了）
      html-overflow  HTML 行横向溢出（scrollWidth > clientWidth）
      v-overflow     HTML 行整体撑破卡片底边
      overlap        两段文字互相压住（rect 求交）
      crosses-line / crosses-frame / crosses-box  文字压到箭头、外框、或穿出方框
      too-tight      上下相邻两行贴得太紧（提示）
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
        # 位置判断用**视觉 rect**（vx/vy/vw/vh）：getBBox 不认父级 transform，
        # 用它判位置会把 chain 这类带 transform 的分组误判成越界（实测 16 条假阳性）
        vx = t.get("vx", t["x"]); vy = t.get("vy", t["y"])
        vw = t.get("vw", t["w"]); vh = t.get("vh", t["h"])
        if vx < -2 or vx + vw > W + 2:
            issues.append({"idx": ti, "kind": "out-of-canvas", "where": "x", "text": t["s"],
                           "real_w": t["w"], "x": vx, "y": vy,
                           "cx": cx, "cy": cy, "size": None})
        if vy + vh > H + 2:
            issues.append({"idx": ti, "kind": "out-of-canvas", "where": "y", "text": t["s"],
                           "y_bottom": vy + vh, "cx": cx, "cy": cy})
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
    # ---- DOM 文字槽：浏览器实测的溢出与孤字（DOM 模式下最权威的一类）----
    for sl in rep.get("slots") or []:
        # 孤字：用真实行盒判 —— 折行是浏览器做的，Python 侧估不准（也不用再维护 wrap_text）
        if (sl.get("lines") or 0) >= 2 and sl.get("lastW", 1) < 0.25 * max(1.0, sl.get("w", 1)):
            issues.append({"kind": "dom-orphan", "tag": "dom",
                           "text": sl.get("text", "")[:30],
                           "note": "末行只剩 %.0f%% 宽（共 %d 行）→ 孤字，建议改短文案"
                                   % (100.0 * sl["lastW"] / max(1.0, sl["w"]), sl["lines"])})
        if sl.get("over"):
            issues.append({"kind": "dom-overflow", "tag": "dom",
                           "text": sl.get("text", "")[:30],
                           "note": "DOM 槽放不下：内容 %dpx 高 / 容器 %dpx（字号 %s，已缩到下限）"
                                   % (sl.get("sh", 0), sl.get("ch", 0), sl.get("fs"))})

    # ---- DOM 文字也参与几何求交（与 SVG 文字对等）----
    # 原来几何门只看 rep.svg（SVG <text>），DOM 文字不在里面 → "压框线/两段压住"反而没人管。
    dom_rects = [(sl["left"], sl["top"], sl["w"], sl["h"], sl.get("text", ""))
                 for sl in (rep.get("slots") or [])]
    if ink and dom_rects:
        for (dx, dy, dw, dh, dtext) in dom_rects:
            for k in ink:
                if k["kind"] == "line" and _overlap((dx, dy, dw, dh), k) > 4:
                    issues.append({"kind": "crosses-line", "tag": "dom", "text": dtext[:30],
                                   "note": "DOM 文字压到箭头/连线"})
                # 侵入深度判据：文字从上方/下方真的"扎进"方框多少像素。
                # 原来用"文字的顶边是否高于框顶 4px"会把"整体在框外、只擦到 1px"也算穿框
                # （实测 mid 与手绘笔锋 overshoot 就是这么误报的）。真穿框是 20px+ 量级。
                elif k["kind"] == "box" and _overlap((dx, dy, dw, dh), k) > 4 \
                        and ((k["y"] - (dy + dh)) if dy < k["y"]
                             else ((dy + dh) - (k["y"] + k["h"]))) > 4:
                    issues.append({"kind": "crosses-box", "tag": "dom", "text": dtext[:30],
                                   "note": "DOM 文字纵向穿出方框（框 y=%.0f~%.0f，文字 y=%.0f~%.0f）"
                                           % (k["y"], k["y"] + k["h"], dy, dy + dh)})
    for i in range(len(dom_rects)):
        for j in range(i + 1, len(dom_rects)):
            a, b = dom_rects[i], dom_rects[j]
            ov = _overlap((a[0], a[1], a[2], a[3]), {"x": b[0], "y": b[1], "w": b[2], "h": b[3]})
            if ov > 4 and ov > 0.08 * max(1.0, min(a[2] * a[3], b[2] * b[3])):
                issues.append({"kind": "overlap", "tag": "dom", "text": b[4][:30],
                               "note": "两段 DOM 文字互相压住：%r × %r" % (a[4][:12], b[4][:12])})

    # ---- 几何布局门：rect 求交（第四道门）----
    # 视觉复核里"压字 / 压线 / 压框"这几类，本质都是包围盒相交，用 rect 量比看图准且免费。
    svg = rep.get("svg", [])
    if ink:
        for ti, t in enumerate(svg):
            r = (t.get("vx", t["x"]), t.get("vy", t["y"]),
                 t.get("vw", t["w"]), t.get("vh", t["h"]))
            for k in ink:
                # ★ frame 不参与求交：外框是"环"，它的 bbox 等于整张画布，
                # 任何卡内文字都会"重叠"（实测刷出 31 条假阳性）。
                # 文字越出安全区由 out-of-canvas 管 —— 环形元素不能靠 bbox 判相交。
                if k["kind"] == "frame":
                    continue
                if k["kind"] == "line":
                    ov = _overlap(r, k)
                    # 阈值：面积 >4px² 且占文字自身 3% 以上，避免"差 1px 擦边"刷屏
                    if ov > 4 and ov > 0.03 * max(1.0, t["w"] * t["h"]):
                        issues.append({
                            "idx": ti, "kind": "crosses-line", "tag": t.get("tag") or "?",
                            "text": t["s"], "area": round(ov, 1),
                            "note": "文字压到箭头/连线（重叠 %.0f px²）" % ov})
                elif k["kind"] == "box":
                    # 横向溢出已有 box-overflow 管，这里只补「纵向穿出」
                    if _overlap(r, k) > 1 and (r[1] < k["y"] - 0.5
                                               or r[1] + r[3] > k["y"] + k["h"] + 0.5):
                        issues.append({
                            "idx": ti, "kind": "crosses-box", "tag": t.get("tag") or "?",
                            "text": t["s"],
                            "note": "文字纵向穿出方框（框 y=%.0f~%.0f，文字 y=%.0f~%.0f）"
                                    % (k["y"], k["y"] + k["h"], r[1], r[1] + r[3])})
    for i in range(len(svg)):
        for j in range(i + 1, len(svg)):
            a, b = svg[i], svg[j]
            av = (a.get("vx", a["x"]), a.get("vy", a["y"]),
                  a.get("vw", a["w"]), a.get("vh", a["h"]))
            bv = (b.get("vx", b["x"]), b.get("vy", b["y"]),
                  b.get("vw", b["w"]), b.get("vh", b["h"]))
            ov = _overlap(av, {"x": bv[0], "y": bv[1], "w": bv[2], "h": bv[3]})
            # 加严阈值：rect 含 ascent/descent，紧邻两行会"盒重叠但字不重叠"。
            # 要求纵向重叠 > 较小高度 25%、横向 > 较小宽度 20%，且面积 > 8%。
            ox = min(av[0] + av[2], bv[0] + bv[2]) - max(av[0], bv[0])
            oy = min(av[1] + av[3], bv[1] + bv[3]) - max(av[1], bv[1])
            min_area = max(1.0, min(av[2] * av[3], bv[2] * bv[3]))
            if (ov > 4 and ov > 0.08 * min_area
                    and oy > 0.25 * min(av[3], bv[3]) and ox > 0.20 * min(av[2], bv[2])):
                issues.append({
                    "idx": j, "kind": "overlap", "tag": b.get("tag") or "?",
                    "text": b["s"], "area": round(ov, 1),
                    "note": "两段文字互相压住：%r × %r（重叠 %.0f px²）"
                            % (a["s"][:14], b["s"][:14], ov)})
    # ★ 这里故意**不做**"行间距太紧"的提示：它是主观提示，却被算进
    # `measure: N 处溢出`、还会落进宽度桶触发 autofix（实测 matrix 每页刷 10 条、
    # calib 被抬到 1.39）。提示不该进问题列表 —— 要留就留给人工选图时看。
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
    # 墨迹优先用浏览器量到的（DOM 同源）；没有才退回 build 埋的清单
    ink = rep.get("ink") or _ink_of(html_path)
    return rep, analyze(rep, _boxes_of(html_path), _texts_of(html_path), ink)
