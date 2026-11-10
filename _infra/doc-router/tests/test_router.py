"""문서 라우터 대표 요청 모의시험과 구조 검사.

실행: python -m unittest discover -s _infra/doc-router/tests
파일을 쓰지 않고, 실제 설치·생성·업로드를 하지 않는다.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
import router  # noqa: E402

TEMPLATE = "productions/_template"
CYCLE = "craft/doctrine/production-cycle.md"
PLANNING = "craft/doctrine/planning.md"
FORMAT = "craft/doctrine/shorts-format.md"


class RouterTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = router.load_json(router.ROUTES_PATH)

    def paths(self, tags, path=""):
        res = router.select(self.cfg, router.split_tags(tags), path)
        return res, [d["path"] for d in res["docs"]]

    def test_check_passes(self):
        errs, _warns, _info = router.run_check(self.cfg)
        self.assertEqual(errs, [])

    def test_story(self):
        res, p = self.paths("이야기")
        self.assertEqual(res["routes"], ["story-planning"])
        self.assertEqual(p, [CYCLE, PLANNING])

    def test_story_factcheck(self):
        res, p = self.paths("팩트체크")
        self.assertEqual(res["routes"], ["story-planning"])
        self.assertEqual(p, [CYCLE, PLANNING, "craft/doctrine/factcheck-rights.md"])

    def test_prompt(self):
        _, p = self.paths("프롬프트")
        self.assertEqual(p, ["library/prompts/README.md"])

    def test_local_run(self):
        _, p = self.paths("comfyui")
        self.assertEqual(p, ["docs/runbooks/local-generation.md", "library/workflows/README.md"])

    def test_paid(self):
        _, p = self.paths("유료생성")
        self.assertEqual(p, ["docs/runbooks/paid-generation.md"])

    def test_paid_gpt_image(self):
        _, p = self.paths("유료생성 대표그림")
        self.assertEqual(p, ["docs/runbooks/paid-generation.md", "craft/playbooks/gpt-image.md"])

    def test_resume_nearest_order(self):
        _, p = self.paths("재개", TEMPLATE)
        self.assertEqual(p, [f"{TEMPLATE}/생성상태.md", f"{TEMPLATE}/BRIEF.md"])

    def test_resume_without_path_asks(self):
        res, p = self.paths("재개")
        self.assertEqual(p, [])
        self.assertTrue(any("경로" in n for n in res["notes"]))

    def test_review(self):
        _, p = self.paths("검수", TEMPLATE)
        self.assertEqual(p, ["docs/runbooks/review-delivery.md",
                             f"{TEMPLATE}/renders.md", f"{TEMPLATE}/생성상태.md"])

    def test_review_assemble(self):
        _, p = self.paths("조립")
        self.assertEqual(p, ["docs/runbooks/review-delivery.md", "craft/playbooks/post-production.md"])

    def test_review_thumbnail(self):
        _, p = self.paths("썸네일")
        self.assertEqual(p, ["docs/runbooks/review-delivery.md", FORMAT])

    def test_performance(self):
        res, p = self.paths("성과", TEMPLATE)
        self.assertEqual(res["routes"], ["performance"])
        self.assertEqual(p, ["private/README.md", f"{TEMPLATE}/renders.md"])

    def test_repo_docs(self):
        _, p = self.paths("문서구조")
        self.assertEqual(p, ["docs/agent/README.md"])

    def test_dedupe_across_routes(self):
        _, p = self.paths("재개 로컬실행", TEMPLATE)
        self.assertEqual(len(p), len(set(p)))

    def test_no_route(self):
        res, p = self.paths("아무거나")
        self.assertEqual(res["status"], "no_route")
        self.assertEqual(p, [])

    def test_forbidden_never_selected(self):
        for tag in router.BASE_ROUTE_IDS + ["performance"]:
            _, p = self.paths(tag, TEMPLATE)
            for x in p:
                self.assertFalse(router.is_forbidden(self.cfg, x), x)
                self.assertNotIn(x, ("CONTEXT.md", "renders.md"))

    def test_no_private_docs_in_routes(self):
        for r in self.cfg["routes"]:
            docs = list(r["read_order"])
            for c in r["conditional_docs"]:
                docs += c.get("read_order", [])
            for d in docs:
                if d.startswith("private/"):
                    self.assertEqual(d, "private/README.md")

    def test_path_rejections(self):
        for bad in ("../outside", "/etc/passwd", "C:/Windows", "productions\\x", "productions/../.."):  # public-check: allow
            with self.assertRaises(router.RouterError):
                router.select(self.cfg, ["재개"], bad)

    def test_shorts_h3_prompt(self):
        res, p = self.paths("프롬프트 h3 쇼츠")
        self.assertEqual(res["routes"], ["prompt-writing"])
        self.assertEqual(res["unknown_tags"], [])
        self.assertEqual(p, ["library/prompts/README.md",
                             "craft/playbooks/minimax-h3-r2v.md",
                             "library/prompts/minimax-h3/r2v-block-skeleton.md",
                             FORMAT])

    def test_shorts_h3_local_run(self):
        _, p = self.paths("로컬실행 h3")
        self.assertEqual(p, ["docs/runbooks/local-generation.md",
                             "library/workflows/h3-r2v-speedx6/README.md"])

    def test_shorts_story(self):
        _, p = self.paths("기획 쇼츠")
        self.assertEqual(p, [CYCLE, PLANNING, FORMAT])

    def test_full_story_route_within_limit(self):
        res, _ = self.paths("기획 쇼츠 팩트체크")
        self.assertNotEqual(res["status"], "over_limit")

    def test_modifier_alone_is_no_route(self):
        res, _ = self.paths("h3")
        self.assertEqual(res["status"], "no_route")

    def test_all_base_routes_linked(self):
        linked = {r for v in self.cfg["representative_tags"].values() for r in v}
        for rid in router.BASE_ROUTE_IDS:
            self.assertIn(rid, linked)


if __name__ == "__main__":
    unittest.main()
