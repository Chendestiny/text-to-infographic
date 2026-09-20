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


# ─────────────────────────────── 5. 可靠性兜底
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
