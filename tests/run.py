# -*- coding: utf-8 -*-
"""text-to-infographic 门禁自测 —— 一条命令跑完。

    python tests/run.py            # 全部
    python tests/run.py -v         # 详细
    python tests/run.py TestGates  # 只跑某一组

为什么需要它：本轮（以及前几轮）抓到的 bug 全都属于「文档承诺 A、代码做 B」
或「门没跑却报绿」—— 读代码和读文档都发现不了，只能靠执行。不固化成测试，
下次改渲染链路还会悄悄退化，于是又得多返工几轮（而**轮次**才是墙钟的大头）。

每条测试都对应一次真实的踩坑，注释里写了它守的是什么。

注意：需要能 import yaml（契约本体是 YAML），见 README 的依赖说明。
"""
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "scripts")
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, HERE)

ARTICLE = os.path.join(ROOT, "article",
                       "01-我开源了一个把长文转成自媒体多图的Skill.md")
EXAMPLES_JSON = sorted(
    os.path.join(ROOT, "examples", "json", f)
    for f in os.listdir(os.path.join(ROOT, "examples", "json"))
    if f.endswith(".json"))
EXAMPLES_YAML = sorted(
    os.path.join(ROOT, "examples", f)
    for f in os.listdir(os.path.join(ROOT, "examples"))
    if f.endswith((".yaml", ".yml")))
# hub 在第一页，方便造「硬溢出」
HUB_SPEC = os.path.join(ROOT, "examples", "json", "agent-handbook.json")


def run_script(name, *args, **kw):
    """跑一个 scripts/ 下的脚本，返回 (returncode, 合并输出, 耗时秒)。"""
    env = dict(os.environ)
    env.setdefault("T2I_BACKEND", "cdp")
    env.update(kw.get("env") or {})
    t0 = time.time()
    p = subprocess.run([sys.executable, os.path.join(SCRIPTS, name)]
                       + [str(a) for a in args],
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace", cwd=ROOT, env=env,
                       timeout=kw.get("timeout", 900))
    return p.returncode, (p.stdout or "") + (p.stderr or ""), time.time() - t0


def load(path):
    return json.loads(io.open(path, encoding="utf-8").read())


def dump(obj, path):
    with io.open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(obj, ensure_ascii=False, indent=2))


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp(prefix="t2i-test-")

    def path(self, name):
        return os.path.join(self.tmp, name)


# ─────────────────────────────── 1. 示例规格不该退化
class TestExamples(Base):
    """守：改渲染链路后，已有示例仍然出得来（exit=0）。"""

    def test_json_examples_render(self):
        for spec in EXAMPLES_JSON:
            with self.subTest(spec=os.path.basename(spec)):
                out = os.path.join(self.tmp, "ex-" + os.path.basename(spec)[:-5])
                rc, o, _ = run_script("pipeline.py", spec, "-o", out,
                                      timeout=300)
                self.assertEqual(rc, 0, "%s 失败：\n%s" % (spec, o[-1500:]))

    def test_yaml_examples_pass_spec_gate(self):
        """yaml 版只过规格门（不启浏览器），守住「两种格式都能读」。"""
        for spec in EXAMPLES_YAML:
            with self.subTest(spec=os.path.basename(spec)):
                rc, o, _ = run_script("validate.py", spec, timeout=120)
                self.assertIn("契约校验", o, "%s 规格门没跑完：\n%s" % (spec, o[-800:]))


# ─────────────────────────────── 2. 严重度分级
class TestSeverity(unittest.TestCase):
    """守：dom-orphan 是提示、dom-overflow 是硬问题。

    踩坑：两者曾同桶 → 一条孤字让整轮 exit=1，白跑 2 轮返工。
    """

    @staticmethod
    def _verify(kinds):
        import pipeline
        st = {"issues": {"card-01": [{"kind": k, "text": "文案", "note": "说明"}
                                     for k in kinds]}}
        pipeline.node_verify(st)
        return st

    def test_orphan_is_soft_not_blocking(self):
        st = self._verify(["dom-orphan"])
        self.assertEqual(len(st["soft_issues"]), 1)
        self.assertEqual(st["layout_issues"], [])
        self.assertEqual(st["width_issues"], {})

    def test_overflow_still_blocks(self):
        st = self._verify(["dom-overflow"])
        self.assertEqual(len(st["layout_issues"]), 1)
        self.assertEqual(st["soft_issues"], [])

    def test_geometry_issues_still_block(self):
        for kind in ("overlap", "crosses-box", "crosses-line", "v-overflow",
                     "missing-text"):
            st = self._verify([kind])
            self.assertEqual(len(st["layout_issues"]), 1,
                             "%s 应该算硬问题" % kind)


# ─────────────────────────────── 3. 报错要说清楚
class TestReporting(Base):
    """守：报错必须带实测值、必须点名、必须说清门有没有跑。"""

    def test_overflow_report_carries_px(self):
        """踩坑：needs_llm 把 issue 的 note（像素值）丢了，只说"这条不行"。"""
        spec = load(HUB_SPEC)
        spec["cards"][0]["items"][0]["big"] = "超" * 40
        p = self.path("overflow.json")
        dump(spec, p)
        rc, o, _ = run_script("pipeline.py", p, "-o", self.path("ovf"),
                              timeout=300)
        self.assertEqual(rc, 1, "真溢出应该拦住：\n%s" % o[-1200:])
        self.assertIn("px", o, "报错必须带像素值：\n%s" % o[-1200:])
        self.assertIn("card-01", o, "报错必须点名是哪一页：\n%s" % o[-1200:])

    def test_spec_gate_failure_is_not_swallowed(self):
        """踩坑：validate.py 崩了（缺 pyyaml）→ 输出里既没有"契约校验"也没有
        "契约违规"，run.py 把它落进「有提示，见下」，继续报 exit=0。"""
        spec = load(HUB_SPEC)
        spec["cards"][0]["items"] = []          # 硬违规
        p = self.path("badspec.json")
        dump(spec, p)
        rc, o, _ = run_script("validate.py", p, timeout=120)
        # 不管通过还是违规，都必须有稳定的结论行
        self.assertTrue(("契约校验" in o) or ("契约违规" in o),
                        "规格门必须输出稳定结论行：\n%s" % o[-800:])


# ─────────────────────────────── 4. 页数与预算
class TestPlanAndBudget(Base):
    """守：plan 的偏离理由认对键；--budget 不许报假绿。"""

    @staticmethod
    def _spec_with_plan(n_cards, suggest, note):
        cards = [{"layout": "bullets", "title": "T%d" % i, "subtitle": "S",
                  "items": [{"head": "H", "desc": "D"}]}
                 for i in range(n_cards)]
        return {"meta": {"plan": {"suggest": suggest, "range": [4, 9],
                                  "note": note}},
                "cards": cards}

    def test_plan_note_is_accepted(self):
        """踩坑：plan.py 只读 meta.plan_note，而它自己打印的模板写 meta.plan.note
        —— 照文档填了却被判「没写偏离理由」。"""
        p = self.path("plan-note.json")
        dump(self._spec_with_plan(6, 5, "理由：两节合并更顺"), p)
        rc, o, _ = run_script("plan.py", ARTICLE, "--check", p, timeout=120)
        self.assertIn("偏离理由已记录", o, "填了 note 就别再警告：\n%s" % o[-800:])

    def test_missing_plan_note_warns(self):
        p = self.path("plan-nonote.json")
        dump(self._spec_with_plan(6, 5, ""), p)
        rc, o, _ = run_script("plan.py", ARTICLE, "--check", p, timeout=120)
        self.assertIn("没写偏离理由", o, "没填 note 应该警告：\n%s" % o[-800:])

    def test_budget_never_reports_false_all_clear(self):
        """踩坑：_CAPS 恒空 → --budget 对已知会溢出的规格照样报「都放得下 ✓」。"""
        spec = load(HUB_SPEC)
        spec["cards"][0]["items"][0]["big"] = "超" * 40
        p = self.path("budget.json")
        dump(spec, p)
        rc, o, _ = run_script("capacity.py", p, "--budget", timeout=120)
        self.assertNotIn("所有槽在标准字号下都放得下", o,
                         "--budget 不许报假绿：\n%s" % o[-800:])


# ─────────────────────────────── 5. 版式烟雾测试
# 守：13 种版式每一种都能出图。写成**一张包含全部版式的规格**跑一次，
#     而不是 13 次单独跑（各自 ~5s，合起来太慢）。
#     坏处是失败时只说"这套没出全"，好处是便宜 —— 而这套测试的核心目的就是便宜。
LAYOUT_CARDS = {
    "cover": {"layout": "cover", "title": "T", "subtitle": "S",
              "quads": [{"label": "L", "mini": "steps",
                         "items": [{"text": "A"}, {"text": "B"}, {"text": "C"}]}]},
    "cover_title": {"layout": "cover_title", "title": "第一行\n第二行\n第三行",
                    "kicker": "标签", "subtitle": "支撑句"},
    "cover_quote": {"layout": "cover_quote", "quote": "把结论写在第一页",
                    "source": "出处"},
    "hub": {"layout": "hub", "title": "T", "hub": "H",
            "items": [{"big": "A", "en": "a"}, {"big": "B", "en": "b"}]},
    "chain": {"layout": "chain", "title": "T",
              "steps": [{"text": "第一步"}, {"text": "第二步"}, {"text": "第三步"}]},
    "cycle": {"layout": "cycle", "title": "T", "keywords": ["A", "B", "C"],
              "nodes": [{"text": "N1"}, {"text": "N2"}, {"text": "N3"}]},
    "spectrum": {"layout": "spectrum", "title": "T", "stages": ["一", "二"],
                 "ends": ["左", "右"],
                 "items": [{"text": "第一条"}, {"text": "第二条"}, {"text": "第三条"}]},
    "timeline": {"layout": "timeline", "title": "T",
                 "steps": [{"text": "S1", "desc": "d"}, {"text": "S2", "desc": "d"},
                           {"text": "S3", "desc": "d"}]},
    "flow": {"layout": "flow", "title": "T",
             "nodes": [{"text": "N1", "desc": "d"}, {"text": "N2", "desc": "d"},
                       {"text": "N3", "desc": "d"}]},
    "bullets": {"layout": "bullets", "title": "T",
                "items": [{"head": "H1", "desc": "d"}, {"head": "H2", "desc": "d"}]},
    "compare": {"layout": "compare", "title": "T",
                "left": {"label": "L", "blocks": ["A", "B"]},
                "right": {"label": "R", "blocks": ["C", "D"]}},
    "matrix": {"layout": "matrix", "title": "T",
               "cells": [{"head": "C1", "desc": "d"}, {"head": "C2", "desc": "d"},
                         {"head": "C3", "desc": "d"}, {"head": "C4", "desc": "d"}]},
    "pyramid": {"layout": "pyramid", "title": "T",
                "levels": [{"text": "顶层"}, {"text": "中层"}, {"text": "基座"}]},
    "arch": {"layout": "arch", "title": "T", "host_label": "H",
             "inner": [{"text": "I1", "desc": "d"}], "server": "S",
             "chips": [{"text": "C1"}, {"text": "C2"}]},
    "raw": {"layout": "raw",
            "svg": "<svg class='stage' width='824' height='600' "
                   "xmlns='http://www.w3.org/2000/svg'><rect x='20' y='20' "
                   "width='300' height='120' rx='12' fill='#F2C94C' "
                   "stroke='#2B2B2B' stroke-width='5'/></svg>"},
}


class TestLayoutSmoke(Base):
    def test_every_layout_renders(self):
        names = list(LAYOUT_CARDS)
        spec = {"meta": {}, "cards": [LAYOUT_CARDS[n] for n in names]}
        p = self.path("layouts.json")
        dump(spec, p)
        out = self.path("layouts")
        rc, o, _ = run_script("pipeline.py", p, "-o", out, timeout=300)
        self.assertEqual(rc, 0, "版式烟雾测试失败：\n%s" % o[-2000:])
        missing = [n for i, n in enumerate(names, 1)
                   if not os.path.exists(os.path.join(out, "card-%02d.png" % i))
                   or os.path.getsize(os.path.join(out, "card-%02d.png" % i)) < 1024]
        self.assertEqual(missing, [], "这些版式没出图：%s" % missing)

    def test_unsupported_field_is_reported(self):
        """守：写了不渲染的字段要被点名（原来会静默消失）。

        layouts.md：note 只在 arch/chain/cover/flow/hub/matrix/pyramid/spectrum/
        timeline 上渲染，bullets / compare / cycle / raw 写了不渲染。
        """
        spec = {"meta": {}, "cards": [
            {"layout": "bullets", "title": "T", "note": "这里不会被渲染",
             "items": [{"head": "H", "desc": "d"}]}]}
        p = self.path("badfield.json")
        dump(spec, p)
        rc, o, _ = run_script("validate.py", p, timeout=120)
        self.assertIn("契约校验", o, "规格门没跑完：\n%s" % o[-800:])
        self.assertTrue(("字段提示" in o) or ("note" in o),
                        "写了不渲染的字段应该被点名：\n%s" % o[-800:])


# ─────────────────────────────── 6. 版式级反例
class TestCounterExamples(unittest.TestCase):
    """压框 / 压线 / 劈词。

    压框压线靠真实渲染很难稳定造出来（得先让浏览器真的把字放偏），
    所以这里直接给 `measure.analyze()` 喂合成的测量报告 —— 不启浏览器，
    于是每条都是确定性的、也就跑得动。
    """

    @staticmethod
    def _analyze(slots, ink):
        import measure
        rep = {"stage": {"w": 824, "h": 900}, "svg": [], "html": [],
               "slots": slots,
               "text": " ".join(s.get("text", "") for s in slots)}
        return measure.analyze(rep, boxes=None, texts=None, ink=ink)

    @staticmethod
    def _slot(text="文案", left=100, top=100, w=300, h=60):
        return {"left": left, "top": top, "w": w, "h": h, "sh": h,
                "text": text}

    def test_dom_text_crossing_a_line_is_caught(self):
        kinds = [i["kind"] for i in self._analyze(
            [self._slot("压住线的文字")],
            [{"kind": "line", "x": 110, "y": 110, "w": 280, "h": 40}])]
        self.assertIn("crosses-line", kinds)

    def test_dom_text_crossing_a_box_is_caught(self):
        # 穿框的判据不是"有重叠"，而是"文字从框内**纵向扎出底边**"——
        # 文字完整落在框里是正常的（色块本来就在字底下），只有扎出去才算。
        # 所以这里让文字起点在框内、底边越过框底 20px。
        kinds = [i["kind"] for i in self._analyze(
            [self._slot("扎出框底的文字", top=180, h=60)],
            [{"kind": "box", "x": 100, "y": 120, "w": 300, "h": 100}])]
        self.assertIn("crosses-box", kinds)

    def test_no_overlap_means_no_issue(self):
        """反向用例：不重叠就不该报 —— 防止上面两条变成"永远报"。"""
        self.assertEqual(self._analyze(
            [self._slot("安分的文字", w=100, h=40)],
            [{"kind": "line", "x": 600, "y": 700, "w": 10, "h": 10}]), [])

    def test_css_never_splits_inside_a_word(self):
        """劈词（断词）：DOM 侧靠 CSS 保证，**不是门检出来的**。

        所以一旦有人把 `word-break` 改成 break-all / anywhere，
        四道门一声不响，整批图却开始劈词 —— 这类回归只能靠守住那条 CSS。
        """
        css = io.open(os.path.join(SCRIPTS, "ink.py"), encoding="utf-8").read()
        self.assertIn("overflow-wrap: break-word", css,
                      "缺 overflow-wrap: break-word，长词会顶破容器")
        self.assertIn("word-break: normal", css,
                      "缺 word-break: normal，拉丁词可能被从中间劈开")
        self.assertNotIn("word-break: break-all", css,
                         "break-all 会在词内断行（劈词）")
        self.assertNotIn("overflow-wrap: anywhere", css,
                         "anywhere 会在词内断行（劈词）")


# ─────────────────────────────── 7. 主题（皮肤）
class TestTheme(unittest.TestCase):
    """守：一套令牌换掉全部像素 —— 不能只换一半。

    主题最容易出的失效是"换了一半"：颜色换了、笔锋没换（深色主题配手绘抖线），
    或者文字色没跟着底色走（深色主题的白字压在亮黄块上）。
    这几种都不会让任何一道门报警，只会让图变丑，所以只能靠单测钉住。
    """

    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, SCRIPTS)
        import ink  # noqa: F401

    def setUp(self):
        import ink
        self.ink = ink

    def test_every_theme_applies_its_tokens(self):
        import theme
        for k in theme.names():
            t = self.ink.use_theme(k)
            self.assertEqual(self.ink.INK, t["ink"], k)
            self.assertEqual(self.ink.BG_CARD, t["bg_card"], k)
            self.assertEqual(self.ink.PAL, t["pal"], k)
            self.assertEqual(self.ink.WOBBLE, t["wobble"], k)
        self.ink.use_theme(theme.DEFAULT)          # 别把默认皮肤留在别人身上

    def test_zero_wobble_means_a_straight_line(self):
        """守：`wobble: 0` 必须真的产出直线。

        判据是「边的段数」：手绘边是 1 段主线 + 3 段收笔 = 4 段，
        几何边收成 1 段。段数不变就说明主题没作用到墨迹上。
        """
        self.ink.use_theme("crayon")
        self.assertGreater(len(self.ink.pen_rect(10, 10, 100, 50, 1)), 4)
        self.ink.use_theme("terminal")
        self.assertEqual(len(self.ink.pen_rect(10, 10, 100, 50, 1)), 4)
        # 直线段里不该出现偏离端点的坐标
        d = self.ink.pen_rect(10, 10, 100, 50, 1)[0][0]
        self.assertIn("M", d)
        self.assertEqual(d, "M10.0 10.0 L110.0 10.0")

    def test_unknown_theme_raises_instead_of_falling_back(self):
        """守：主题名写错要当场报错。

        静默回落成默认皮肤的表现是"这个主题好像没生效"，比报错难查得多。
        """
        with self.assertRaises(KeyError):
            self.ink.use_theme("no-such-theme")
        with self.assertRaises(ValueError):
            self.ink.render_card({"layout": "bullets", "title": "T"}, 0, 1,
                                 {"theme": "no-such-theme"}, "file:///x.ttf")

    def test_dom_slot_align_is_normalised(self):
        """踩坑：render_card 用 `align == "left"` 判，而 txt()/hl_line() 传的是
        `"start"` —— 两边永远不相等，于是**所有左右对齐的槽一直是居中渲染的**
        （spectrum 两端标签、matrix 轴标签都在其中）。
        """
        self.ink._SLOTS.clear()
        for a in ("start", "left", "end", "right", "middle", "center"):
            self.ink._reg_slot(0, 0, 100, 40, "x", 20, align=a)
        self.assertEqual([s["align"] for s in self.ink._SLOTS],
                         ["left", "left", "right", "right", "center", "center"])

    def test_text_on_a_colored_box_gets_contrast(self):
        """守：文字色要跟着**填充色亮度**走，不是跟着"主题深不深"走。

        踩坑：终端主题的浅灰正文压在亮黄/青/粉块上完全读不出来。
        """
        self.ink.use_theme("terminal")
        self.ink._BOXES.clear()
        self.ink.pen_box(0, 0, 800, 120, 1, "#FFC94D")       # 亮填充 → 深字
        self.ink._SLOTS.clear()
        self.ink._reg_slot(20, 20, 700, 80, "文字", 48)
        self.assertEqual(self.ink._auto_slot_color(self.ink._SLOTS[0]), "#0B1220")
        self.ink._BOXES.clear()
        self.ink.pen_box(0, 0, 800, 120, 1, "#56637F")       # 暗填充 → 浅字
        self.ink._SLOTS.clear()
        self.ink._reg_slot(20, 20, 700, 80, "文字", 48)
        self.assertEqual(self.ink._auto_slot_color(self.ink._SLOTS[0]), "#C6D2E6")

    def test_theme_css_and_hl_shape_reach_the_page(self):
        """守：主题的额外 CSS（网格底纹）与高亮形态要真的进 HTML。"""
        html = self.ink.render_card({"layout": "bullets", "title": "T",
                                     "items": [{"head": "H"}]},
                                    0, 1, {"theme": "terminal"}, "file:///x.ttf")
        self.assertIn("background-size:72px 72px", html, "终端主题的网格底纹没进页面")
        self.assertIn(".hl::before", html, "高亮形态的 CSS 没进页面")
        self.assertNotIn("%RADIUS%", html, "主题占位符没被替换干净")

    def test_every_hl_class_has_a_css_rule(self):
        """守：`[[词]]` 渲染出来的 class 必须真的命中一条 CSS 规则。

        踩坑（潜伏很久，四道门全都没响）：`_inline` 把 `gr` 通过 COLOR_KEY
        映射成**颜色名** `green` 塞进 class，而 CSS 里只定义了 `.hl.gr` ——
        于是 `[[词|gr]]` 和 `hl_line` 重建出来的**所有非默认色高亮一直是透明的**。
        文字在、位置对、不压线，只是没颜色，所以内容门与几何门都抓不到。
        """
        html = self.ink.render_card(
            {"layout": "spectrum", "title": "T", "stages": ["一", "二"],
             "ends": ["左", "右"],
             "items": [{"text": "用 [[甲]]"}, {"text": "用 [[乙]]"}, {"text": "用 [[丙]]"}]},
            0, 1, {}, "file:///x.ttf")
        classes = set(re.findall(r"<span class='hl ([a-z]+)'>", html))
        self.assertTrue(classes, "这一个都没画出高亮，用例本身失效了")
        for c in classes:
            self.assertIn(".hl.%s::before" % c, html,
                          "class %r 没有对应的 CSS 规则（底色会静默变透明）" % c)

    def test_two_families_draw_nodes_differently(self):
        """守：**族**决定节点怎么画 —— 工程族绝不填色。

        用户口径：工程风「框的背景透明（和底色一致）、边框黑色或主题色、没有笔锋笔触」，
        高饱和方框填色在这一族里是不成立的。所以这条测试盯的是节点原语本身：
        纸张族 = 整块填色；工程族 = 透明 + 主题色细描边 + 一处强调。
        """
        self.ink.use_theme("crayon")
        paper = self.ink.node_box(0, 0, 800, 120, 1, "#FFE04D")
        self.assertIn("fill='#FFE04D'", paper, "纸张族应该整块上色")
        self.ink.use_theme("terminal")
        diag = self.ink.node_box(0, 0, 800, 120, 1, "#FFC94D")
        self.assertIn("fill='none'", diag, "工程族的节点必须是透明底（网格要能透进框里）")
        self.assertIn("stroke='%s'" % self.ink.THEME["node_line"], diag,
                      "工程族的描边要用主题色（node_line 默认 = ink）")
        self.assertNotIn("width='800.0' height='120.0' rx='8.0' fill='#FFC94D'", diag,
                         "强调色绝不能当整块填充")
        marks = re.findall(r"<rect[^>]*fill='#FFC94D'[^>]*/>", diag)
        st = self.ink.THEME["node_style"]
        if st == "tab":
            self.assertEqual(len(marks), 1, "角块方案只该有一枚标记：\n%s" % diag)
            self.assertIn("width='%.1f'" % float(self.ink.THEME["tab_size"]), marks[0])
        elif st == "rail":
            self.assertEqual(len(marks), 1, "竖轨方案只该有一条轨：\n%s" % diag)
            self.assertIn("width='%.1f'" % float(self.ink.THEME["rail_w"]), marks[0])
        elif st in ("corner", "double"):
            # 四角刻度 = 4 个角 × 2 段 = 8 段；双线框没有强调色（用描边色画内框）
            self.assertTrue(marks or st == "double", "四角刻度应该画出色段：\n%s" % diag)
        elif st in ("rule", "none"):
            self.assertLessEqual(len(marks), 1, "这套方案不该有多处强调：\n%s" % diag)
        else:
            self.fail("node_style=%r 没被这条测试覆盖" % st)

    def test_diagram_family_has_no_pen_flourish(self):
        """守：工程族**没有笔锋笔触**（用户明确要求）。

        判据：节点 SVG 里一条手绘 `<path>` 都不该有 —— `pen_rect` 那套
        "一条边拆成 4 段收笔"全靠 `<path>`，出现就说明族的分派漏了。
        """
        import theme
        for k in theme.names():
            if theme.get(k)["family"] != "diagram":
                continue
            self.ink.use_theme(k)
            svg = self.ink.node_box(0, 0, 800, 120, 1, "#FFC94D")
            self.assertNotIn("<path", svg, "%s 的节点里出现了手绘 path：\n%s" % (k, svg))
            self.assertIn("stroke-width='%.2f'" % float(self.ink.THEME["node_w"]), svg,
                          "%s 的线宽没跟着 node_w 走（主题令牌没生效）" % k)

    def test_fill_none_really_means_no_fill(self):
        """踩坑：`fill: none` 落到 `PAL.get(x) or pal.next()` 上会**照样上色**，
        和文档承诺的「留白表达这一步不重要」正好相反。三态必须显式判。
        """
        self.ink.use_theme("crayon")
        pal = self.ink.Palette(0)
        self.assertIsNone(self.ink.pick_fill("none", pal))
        self.assertEqual(self.ink.pick_fill("yellow", pal), self.ink.PAL["yellow"])
        self.assertEqual(self.ink.pick_fill(None, pal), self.ink.PAL[self.ink.PAL_ORDER[0]])

    def test_family_defaults_and_membership(self):
        import theme
        for k in theme.names():
            self.assertIn(theme.get(k)["family"], ("paper", "diagram"), k)
        self.assertEqual(theme.get(theme.DEFAULT)["family"], "paper")
        # 两个族都要有人，否则「族」这套机制等于没在用
        fams = {theme.get(k)["family"] for k in theme.names()}
        self.assertEqual(fams, {"paper", "diagram"})

    def test_no_two_themes_share_a_palette(self):
        """守：每套皮肤的调色板要真的不一样 —— 复制粘贴时最容易忘改调色板。"""
        import theme
        seen = {}
        for k in theme.names():
            sig = tuple(theme.get(k)["pal"][c] for c in theme.get(k)["order"])
            self.assertNotIn(sig, seen, "%s 与 %s 调色板完全相同" % (k, seen.get(sig)))
            seen[sig] = k


# ─────────────────────────────── 8. 可靠性兜底
class TestReliability(Base):
    """守：不挂死、不静默失败、不连累好图、单页返工不乱动。"""

    def _full(self, out_name):
        out = self.path(out_name)
        rc, o, sec = run_script("run.py", HUB_SPEC, "--out", out, timeout=300)
        return out, rc, o, sec

    def test_timeout_is_bounded(self):
        """踩坑：run.py 的 subprocess.run 没有 timeout → 一道门挂住就是无限等。"""
        t0 = time.time()
        rc, o, _ = run_script("run.py", HUB_SPEC, "--out", self.path("to"),
                              timeout=300, env={"T2I_TIMEOUT_SCALE": "0.002"})
        elapsed = time.time() - t0
        self.assertNotEqual(rc, 0, "超时必须判失败：\n%s" % o[-1200:])
        self.assertIn("超时", o, "必须明说超时：\n%s" % o[-1200:])
        self.assertLess(elapsed, 240, "超时场景 4 分钟内必须结束，实测 %.0fs" % elapsed)

    def test_render_failure_keeps_good_pages_and_reports(self):
        """踩坑：node_render 先删光所有 PNG 再渲染 → 1 张失败把整套都带走；
        而且失败只进日志、退出码仍是 0。"""
        out, rc, o, _ = self._full("rf")
        self.assertEqual(rc, 0, "基线交付失败：\n%s" % o[-1200:])
        pngs = sorted(f for f in os.listdir(out) if f.endswith(".png"))
        self.assertTrue(pngs, "基线应该出图")
        victim = os.path.join(out, pngs[2])
        os.remove(victim)
        os.mkdir(victim)                       # 让它写不进去
        try:
            rc2, o2, _ = run_script("pipeline.py", HUB_SPEC, "-o", out,
                                    timeout=300)
            self.assertNotEqual(rc2, 0, "渲染失败必须非零退出：\n%s" % o2[-1200:])
            kept = [f for f in os.listdir(out)
                    if f.endswith(".png") and f != os.path.basename(victim)]
            self.assertEqual(len(kept), len(pngs) - 1,
                             "失败只该少这一张，其余好图必须保留（实测 %d/%d）"
                             % (len(kept), len(pngs) - 1))
            rc3, o3, _ = run_script("run.py", HUB_SPEC, "--out", out,
                                    timeout=300)
            self.assertIn("产物｜", o3, "run.py 必须点名缺哪张：\n%s" % o3[-1200:])
        finally:
            os.rmdir(victim)

    def test_only_reworks_one_page(self):
        """守：--only N 只动第 N 页，其余页的 PNG 字节/时间戳都不变。"""
        out, rc, o, _ = self._full("only")
        self.assertEqual(rc, 0, "基线交付失败：\n%s" % o[-1200:])
        before = {f: os.path.getmtime(os.path.join(out, f))
                  for f in os.listdir(out) if f.endswith(".png")}
        self.assertGreaterEqual(len(before), 3)
        target = sorted(before)[1]
        n = int(target[5:7])
        rc2, o2, _ = run_script("run.py", HUB_SPEC, "--only", n, "--out", out,
                                timeout=300)
        self.assertEqual(rc2, 0, "单页返工失败：\n%s" % o2[-1200:])
        after = {f: os.path.getmtime(os.path.join(out, f))
                 for f in os.listdir(out) if f.endswith(".png")}
        changed = [f for f in before if after.get(f) != before[f]]
        self.assertEqual(changed, [target],
                         "只该 %s 变，实际变了 %s" % (target, changed))

    def test_only_out_of_range_is_rejected(self):
        rc, o, _ = run_script("pipeline.py", HUB_SPEC, "-o", self.path("oor"),
                              "--only", 999, timeout=300)
        self.assertNotEqual(rc, 0, "越界页号必须报错")
        self.assertIn("越界", o)


if __name__ == "__main__":
    unittest.main(verbosity=2)
