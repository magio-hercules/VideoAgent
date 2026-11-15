"""에피소드 기계용 상태 검사 시험.

실행: python -m unittest discover -s _infra/episode-state/tests
저장소 파일을 고치지 않는다. 인계 검사는 임시 폴더에서 한다.
"""
import copy
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import episode_state as es  # noqa: E402

TEMPLATE = "productions/_template"

READY = {
    "schema": es.SCHEMA,
    "episode": "EP031",
    "topic": "시험 소재",
    "stage": 5,
    "status": "handoff_ready",
    "assignee": "claude",
    "handoff": {"status": "ready", "at": "2026-11-11T10:00+09:00", "note": ""},
    "versions": {"script": "v03", "style": "S2", "representative": "v1",
                 "timeline": "가안", "meta": None, "video": None},
    "block_count": 2,
    "next_action": "6단계: 나레이션 견적",
    "pending_operator": [],
    "updated_at": "2026-11-11T10:00+09:00",
    "updated_by": "chatgpt",
}


def state(**kw):
    s = copy.deepcopy(READY)
    for k, v in kw.items():
        s[k] = v
    return s


class ParseTests(unittest.TestCase):
    def test_template_is_valid(self):
        s = es.load(es.resolve_episode_dir(TEMPLATE))
        self.assertEqual(es.validate(s), [])
        self.assertEqual(s["assignee"], "chatgpt")

    def test_missing_block(self):
        with self.assertRaises(es.StateError):
            es.parse_text("# 생성상태\n내용만 있음\n")

    def test_two_blocks_rejected(self):
        b = "```json videoagent-state\n{}\n```\n"
        with self.assertRaises(es.StateError):
            es.parse_text(b + b)

    def test_bad_json(self):
        with self.assertRaises(es.StateError):
            es.parse_text("```json videoagent-state\n{\"a\": }\n```\n")

    def test_path_rejections(self):
        for bad in ("../outside", "/etc", "C:/Windows", "productions\\x", ""):  # public-check: allow
            with self.assertRaises(es.StateError):
                es.resolve_episode_dir(bad)


class ValidateTests(unittest.TestCase):
    def test_ready_ok(self):
        self.assertEqual(es.validate(state()), [])

    def test_unknown_field(self):
        s = state()
        s["extra"] = 1
        self.assertTrue(any("정의되지 않은" in e for e in es.validate(s)))

    def test_bad_enum(self):
        self.assertTrue(es.validate(state(status="finished")))
        self.assertTrue(es.validate(state(assignee="gpt")))

    def test_ready_requires_stage5_and_claude(self):
        self.assertTrue(es.validate(state(stage=4)))
        self.assertTrue(es.validate(state(assignee="chatgpt")))

    def test_ready_requires_time(self):
        s = state()
        s["handoff"]["at"] = None
        self.assertTrue(es.validate(s))

    def test_status_handoff_mismatch(self):
        s = state()
        s["handoff"]["status"] = "none"
        self.assertTrue(es.validate(s))

    def test_waiting_pc_is_claude(self):
        s = state(stage=7, status="waiting_pc", assignee="claude")
        s["handoff"]["status"] = "accepted"
        self.assertEqual(es.validate(s), [])
        s["assignee"] = "operator"
        self.assertTrue(es.validate(s))

    def test_chatgpt_not_after_stage6(self):
        s = state(stage=6, status="active", assignee="chatgpt")
        s["handoff"]["status"] = "accepted"
        self.assertTrue(any("6단계" in e for e in es.validate(s)))

    def test_waiting_operator_needs_items(self):
        s = state(stage=3, status="waiting_operator", assignee="operator")
        s["handoff"]["status"] = "none"
        self.assertTrue(es.validate(s))
        s["pending_operator"] = ["대본 v03 승인"]
        self.assertEqual(es.validate(s), [])

    def test_decision_card_items(self):
        s = state(stage=9, status="waiting_operator", assignee="operator")
        s["handoff"]["status"] = "accepted"
        s["pending_operator"] = [
            "Drive 업로드 여부",
            {"id": "thumb", "question": "썸네일 고르기", "kind": "choose", "options": ["T1", "T2"], "recommend": "T2"},
            {"question": "나레이션 3크레딧", "kind": "cost"},
        ]
        self.assertEqual(es.validate(s), [])

    def test_decision_card_errors(self):
        bad = [
            {"kind": "info"},                                            # question 없음
            {"question": "q", "kind": "vote"},                           # 모르는 kind
            {"question": "q", "kind": "choose", "options": ["하나"]},     # 선택지 부족
            {"question": "q", "options": ["A", "B"], "recommend": "C"},  # 추천이 선택지 밖
            {"question": "q", "id": "공백 있음"},                         # id 형식
            {"question": "q", "extra": 1},                               # 정의 안 된 필드
            "",                                                          # 빈 문자열
            3,                                                           # 형식
        ]
        for item in bad:
            s = state(stage=3, status="waiting_operator", assignee="operator")
            s["handoff"]["status"] = "none"
            s["pending_operator"] = [item]
            self.assertTrue(es.validate(s), item)

    def test_stage_log(self):
        s = state()
        s["stage_log"] = [{"stage": 1, "started_at": "2026-11-13T17:20+09:00", "ended_at": None},
                          {"stage": 0, "started_at": "2026-11-11", "ended_at": "2026-11-11", "note": "날짜만 앎"}]
        self.assertEqual(es.validate(s), [])
        for bad in ({"stage": 12, "started_at": "2026-11-13"}, {"stage": 1, "started_at": "어제"},
                    {"stage": 1, "started_at": "2026-11-13T10:00"}, {"stage": 1, "started_at": "2026-11-13", "x": 1}):
            s["stage_log"] = [bad]
            self.assertTrue(es.validate(s), bad)
        s["stage_log"] = "아님"
        self.assertTrue(es.validate(s))

    def test_bool_is_not_int(self):
        self.assertTrue(es.validate(state(stage=True)))

    def test_time_needs_zone(self):
        self.assertTrue(es.validate(state(updated_at="2026-11-11T10:00")))


class HandoffTests(unittest.TestCase):
    def make(self, pngs, brief=True):
        d = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, d, True)
        if brief:
            open(os.path.join(d, "BRIEF.md"), "w", encoding="utf-8").close()
        sub = os.path.join(d, "05_제작", "대표이미지")
        os.makedirs(sub)
        for n in pngs:
            open(os.path.join(sub, n), "wb").close()
        return d

    def test_all_present(self):
        d = self.make(["EP031_B01_representative.png", "EP031_B02_representative.png"])
        self.assertEqual(es.handoff_problems(d, state()), [])

    def test_missing_block_image(self):
        d = self.make(["EP031_B01_representative.png"])
        probs = es.handoff_problems(d, state())
        self.assertTrue(any("B02" in p for p in probs))

    def test_split_block_counts(self):
        d = self.make(["EP031_B01_representative.png", "EP031_B02a_representative.png"])
        self.assertEqual(es.handoff_problems(d, state()), [])

    def test_missing_versions_and_brief(self):
        s = state()
        s["versions"]["style"] = None
        d = self.make(["EP031_B01_representative.png", "EP031_B02_representative.png"], brief=False)
        probs = es.handoff_problems(d, s)
        self.assertTrue(any("style" in p for p in probs))
        self.assertTrue(any("BRIEF" in p for p in probs))


class CliTests(unittest.TestCase):
    def test_check_template(self):
        self.assertEqual(es.main(["check", TEMPLATE]), 0)

    def test_check_bad_path(self):
        self.assertEqual(es.main(["check", "../x"]), 2)

    def test_list_runs(self):
        self.assertIn(es.main(["list", "--json"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
