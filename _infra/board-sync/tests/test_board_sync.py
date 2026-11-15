"""board_sync 단위 시험. 실제 회차 목록·보드를 쓰지 않는다(가짜 표와 임시 폴더만).

실행: python -m unittest discover -s _infra/board-sync/tests
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import board_sync as bs  # noqa: E402

INDEX = """# 회차 목록

| 회차 | 소재 | 작업 코드 | Drive 납품물 | 상태 | 공개일·URL |
|---|---|---|---|---|---|
| EP001~010 | (이전 프로젝트) | — | 폴더 | Drive 납품 | 미확인 |
| EP011 | 미확인 | — | 없음 | 미확인 | 미확인 |
| EP012 | 가나다 | `A12` | 영상·메타 | Drive 납품 | 2026-10-01 |
| 파일럿 | 시험 편 | pilot | 없음 | 최종본 검수 완료 | 미확인 |
| EP900 | 상태 블록과 겹침 | X900 | 영상 | Drive 납품 | 미확인 |
| **EP901** | (다음 편) | — | — | — | — |
"""

STATE = """# 생성상태

## 기계용 상태

```json videoagent-state
{
  "schema": "videoagent.episode-state/1",
  "episode": "EP900",
  "topic": "상태 블록 쪽 소재",
  "stage": 6,
  "status": "waiting_pc",
  "assignee": "claude",
  "handoff": {"status": "accepted", "at": "2026-11-11T10:00+09:00", "note": ""},
  "versions": {"script": "v01", "style": "S1", "representative": "v1", "timeline": null, "meta": null, "video": null},
  "block_count": 3,
  "next_action": "ComfyUI 켜지면 시험 클립",
  "pending_operator": [],
  "updated_at": "2026-11-11T10:00+09:00",
  "updated_by": "claude"
}
```
"""


class ParseTests(unittest.TestCase):
    def test_rows_and_next_skipped(self):
        rows = bs.parse_index(INDEX)
        self.assertEqual([r["label"] for r in rows], ["EP001~010", "EP011", "EP012", "파일럿", "EP900"])
        self.assertEqual(rows[2]["work_code"], "A12")  # 백틱 제거

    def test_index_doc_mapping(self):
        rows = bs.parse_index(INDEX)
        did, d = bs.index_doc(rows[0], 0)
        self.assertEqual((did, d["order"], d["status"], d["stage"]), ("EP001-010", 1, "delivered", 9))
        did, d = bs.index_doc(rows[1], 0)
        self.assertEqual((did, d["topic"], d["status"], d["stage"]), ("EP011", None, "unknown", None))
        did, d = bs.index_doc(rows[2], 0)
        self.assertEqual(d["published"], "2026-10-01")
        did, d = bs.index_doc(rows[3], 1)
        self.assertEqual((did, d["order"], d["stage"]), ("PILOT1", -1, 8))


class BuildTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="bsync-")
        self.ep = os.path.join(self.tmp, "EP900_시험")
        os.makedirs(self.ep)
        with open(os.path.join(self.ep, "생성상태.md"), "w", encoding="utf-8") as f:
            f.write(STATE)

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_state_overrides_index_and_keeps_extra(self):
        docs, problems = bs.build(INDEX, [self.ep])
        self.assertEqual(problems, [])
        d = docs["EP900"]
        self.assertEqual((d["source"], d["stage"], d["status"]), ("state", 6, "waiting_pc"))
        self.assertEqual(d["topic"], "상태 블록 쪽 소재")
        self.assertEqual(d["work_code"], "X900")  # 회차 목록에만 있던 값은 보탬
        self.assertNotIn("synced_at", d)  # 시각은 meta/sync에만 — 문서 내용이 같으면 지문도 같다
        self.assertEqual(d["content_hash"], bs.content_hash(d))
        self.assertNotIn("EP901", docs)

    def test_hash_stable_and_changed_ids(self):
        a, _ = bs.build(INDEX, [self.ep])
        b, _ = bs.build(INDEX, [self.ep])
        self.assertEqual(a["EP900"]["content_hash"], b["EP900"]["content_hash"])
        committed = {i: d["content_hash"] for i, d in a.items()}
        self.assertEqual(bs.changed_ids(b, committed), [])
        committed["EP012"] = "old"
        self.assertEqual(bs.changed_ids(b, committed), ["EP012"])

    def test_without_index(self):
        docs, _ = bs.build(None, [self.ep])
        self.assertEqual(list(docs), ["EP900"])

    def test_broken_state_reported(self):
        bad = os.path.join(self.tmp, "EP901_깨짐")
        os.makedirs(bad)
        with open(os.path.join(bad, "생성상태.md"), "w", encoding="utf-8") as f:
            f.write("상태 블록 없음")
        docs, problems = bs.build(None, [self.ep, bad])
        self.assertEqual(len(problems), 1)
        self.assertIn("EP900", docs)


TEMPLATE = """# BRIEF — [작품]

## 2. 주제 후보 (1단계)

| 후보 | 이유 |
|---|---|
| [후보] | [이유] |

```text
선택 소재 / 근거
```

## 4. 대본 (3단계)

| 구간 | 나레이션 |
|---|---|
| 도입 | [작성] |
"""

FILLED = TEMPLATE.replace("| [후보] | [이유] |", "| 수능 | 시기 |\n| 호떡 | 겨울 |").replace(
    "## 4. 대본 (3단계)", "## 3. 팩트체크 (2단계)\n\n메모 한 줄\n\n## 4. 대본 (3단계)")


class BriefTests(unittest.TestCase):
    def test_template_parts_dropped(self):
        tmpl = bs.template_keys(TEMPLATE)
        self.assertEqual(bs.parse_brief(TEMPLATE, tmpl), [])  # 견본 그대로면 결과물 없음
        got = bs.parse_brief(FILLED, tmpl)
        self.assertEqual([s["section"] for s in got], ["2", "3"])  # 4절은 견본 그대로라 빠짐
        s2 = got[0]
        self.assertEqual((s2["title"], s2["stages"]), ("주제 후보", [1]))
        self.assertEqual(len(s2["blocks"]), 1)  # 채운 표만 남고 견본 코드 블록은 빠짐
        self.assertEqual(s2["blocks"][0]["rows"], [["수능", "시기"], ["호떡", "겨울"]])
        self.assertEqual(got[1]["blocks"], [{"type": "text", "text": "메모 한 줄"}])

    def test_stage_range(self):
        got = bs.parse_brief("## 5. 스타일 (4~5단계)\n\n내용\n", set())
        self.assertEqual(got[0]["stages"], [4, 5])


class PendingTests(unittest.TestCase):
    def test_normalize(self):
        got = bs.normalize_pending(["Drive 업로드 여부",
                                    {"id": "thumb", "question": "썸네일", "kind": "choose", "options": ["T1", "T2"], "recommend": "T2"},
                                    {"bad": 1}])
        self.assertEqual(len(got), 2)
        self.assertEqual(got[0]["kind"], "info")
        self.assertTrue(got[0]["id"].startswith("p"))
        self.assertEqual(got[0]["id"], bs.normalize_pending(["Drive 업로드 여부"])[0]["id"])  # 같은 글 → 같은 id
        self.assertEqual((got[1]["id"], got[1]["recommend"]), ("thumb", "T2"))


class CliTests(unittest.TestCase):
    def setUp(self):
        self.out = tempfile.mkdtemp(prefix="bsync-out-")
        self.idx = os.path.join(self.out, "index.md")
        with open(self.idx, "w", encoding="utf-8") as f:
            f.write(INDEX)

    def tearDown(self):
        shutil.rmtree(self.out, ignore_errors=True)

    def batch(self):
        import json
        with open(os.path.join(self.out, "batch.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_build_commit_build(self):
        self.assertEqual(bs.main(["build", "--out", self.out, "--index", self.idx]), 0)
        first = self.batch()
        self.assertTrue(any(w["collection"] == "episodes" for w in first))
        self.assertTrue(any(w["collection"] == "meta" for w in first))
        self.assertEqual(bs.main(["commit", "--out", self.out]), 0)
        self.assertEqual(bs.main(["build", "--out", self.out, "--index", self.idx]), 0)
        second = self.batch()
        self.assertEqual([w["collection"] for w in second], ["meta"])  # 바뀐 문서 없음 → meta만
        self.assertEqual(bs.main(["build", "--out", self.out, "--index", self.idx, "--all"]), 0)
        self.assertGreater(len(self.batch()), 1)

    def test_commit_needs_build(self):
        self.assertEqual(bs.main(["commit", "--out", self.out]), 2)


class GuardTests(unittest.TestCase):
    def test_refuses_output_inside_repo(self):
        self.assertEqual(bs.main(["build", "--out", os.path.join(bs.ROOT, "docs", "x")]), 2)


if __name__ == "__main__":
    unittest.main()
