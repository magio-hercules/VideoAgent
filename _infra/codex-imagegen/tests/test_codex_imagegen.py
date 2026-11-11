"""codex_imagegen 단위 시험. Codex를 실행하지 않고, 그림을 생성하지 않는다.

실행: python -m unittest discover -s _infra/codex-imagegen/tests
"""
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import codex_imagegen as ci  # noqa: E402

PNG_1x2 = (b"\x89PNG\r\n\x1a\n" + b"\x00\x00\x00\rIHDR" + (941).to_bytes(4, "big")
           + (1672).to_bytes(4, "big") + b"\x08\x06\x00\x00\x00")


class Tmp(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="cig-test-"))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)


class VersionTests(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(ci.parse_version("codex-cli 0.167.0-alpha.3.2"), (0, 167, 0))
        self.assertEqual(ci.parse_version("codex-cli 0.112.0"), (0, 112, 0))
        self.assertIsNone(ci.parse_version("not found"))

    def test_choose_highest(self):
        p, v = ci.choose_codex([("old", (0, 112, 0)), ("new", (0, 167, 0)), ("bad", None)])
        self.assertEqual((p, v), ("new", (0, 167, 0)))

    def test_choose_tie_keeps_first(self):
        p, _ = ci.choose_codex([("a", (1, 0, 0)), ("b", (1, 0, 0))])
        self.assertEqual(p, "a")

    def test_choose_none_raises(self):
        with self.assertRaises(ci.ToolError):
            ci.choose_codex([("bad", None)])
        with self.assertRaises(ci.ToolError):
            ci.choose_codex([])


class RequestTests(unittest.TestCase):
    def test_targets_single(self):
        self.assertEqual(ci.target_paths(Path("a/EP001_B01_representative.png"), 1),
                         [Path("a/EP001_B01_representative.png")])

    def test_targets_multi(self):
        t = ci.target_paths(Path("a/style.png"), 3)
        self.assertEqual([p.name for p in t], ["style_v01.png", "style_v02.png", "style_v03.png"])

    def test_instruction(self):
        s = ci.build_instruction("  장면 문장  \n", 2, 1)
        self.assertIn("exactly 2 image(s)", s)
        self.assertIn("1 reference image(s)", s)
        self.assertIn("<<<\n장면 문장\n>>>", s)
        self.assertIn("Do not retry", s)
        self.assertNotIn("reference image(s) are attached", ci.build_instruction("x", 1, 0))

    def test_command(self):
        cmd = ci.build_command("codex", "W", ["r1.png", "r2.png"], model=None)
        self.assertEqual(cmd[:2], ["codex", "exec"])
        self.assertIn("image_generation", cmd)
        self.assertEqual(cmd[cmd.index("-s") + 1], "read-only")
        self.assertIn("--image=r1.png", cmd)
        self.assertIn("--image=r2.png", cmd)
        self.assertEqual(cmd[-2:], ["--", "-"])  # 프롬프트는 표준입력
        self.assertNotIn("-m", cmd)
        self.assertIn("-m", ci.build_command("codex", "W", [], model="m1"))


class EventTests(unittest.TestCase):
    def test_success(self):
        text = "\n".join([
            '{"type":"thread.started","thread_id":"T1"}',
            '{"type":"turn.started"}',
            'not json',
            '{"type":"item.completed","item":{"type":"agent_message","text":"DONE 1"}}',
            '{"type":"turn.completed"}',
        ])
        info = ci.parse_events(text)
        self.assertEqual(info["thread_id"], "T1")
        self.assertEqual(info["last_message"], "DONE 1")
        self.assertFalse(info["failed"])

    def test_failure(self):
        text = "\n".join([
            '{"type":"thread.started","thread_id":"T2"}',
            '{"type":"error","message":"needs newer version"}',
            '{"type":"turn.failed","error":{"message":"needs newer version"}}',
        ])
        info = ci.parse_events(text)
        self.assertTrue(info["failed"])
        self.assertIn("needs newer version", info["errors"])


class CollectTests(Tmp):
    def test_collect_and_size(self):
        d = self.tmp / "generated_images" / "T1"
        d.mkdir(parents=True)
        (d / "exec-a.png").write_bytes(PNG_1x2)
        (d / "notes.txt").write_text("x")
        got = ci.collect_images(self.tmp, "T1")
        self.assertEqual([p.name for p in got], ["exec-a.png"])
        self.assertEqual(ci.image_size(got[0]), (941, 1672))
        self.assertEqual(ci.collect_images(self.tmp, "missing"), [])


class MainTests(Tmp):
    def test_refuses_overwrite_before_running(self):
        out = self.tmp / "EP001_B01_representative.png"
        out.write_bytes(PNG_1x2)
        rc = ci.main(["--prompt", "x", "--out", str(out), "--codex", "does-not-exist"])
        self.assertEqual(rc, 2)

    def test_requires_png_and_prompt(self):
        self.assertEqual(ci.main(["--prompt", "x", "--out", str(self.tmp / "a.jpg")]), 2)
        self.assertEqual(ci.main(["--prompt", " ", "--out", str(self.tmp / "a.png")]), 2)
        self.assertEqual(ci.main(["--prompt", "x"]), 2)
        self.assertEqual(ci.main(["--prompt", "x", "--out", str(self.tmp / "a.png"), "--count", "9"]), 2)

    def test_missing_ref(self):
        rc = ci.main(["--prompt", "x", "--out", str(self.tmp / "a.png"), "--ref", str(self.tmp / "no.png")])
        self.assertEqual(rc, 2)


if __name__ == "__main__":
    unittest.main()
