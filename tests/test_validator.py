import unittest

from ai_commit_pr_generator import validator
from ai_commit_pr_generator.config import Format


class CommitTest(unittest.TestCase):
    def test_long_title_truncated(self):
        text, warns = validator.fix_commit("feat: " + "가" * 100)
        self.assertLessEqual(len(text.splitlines()[0]), Format.COMMIT_TITLE_MAX)
        self.assertTrue(warns)

    def test_body_without_bullet_gets_bullet(self):
        text, _ = validator.fix_commit("fix: 버그 수정\n\n파일 a.py 수정")
        self.assertIn("- 파일 a.py 수정", text)

    def test_code_fence_removed(self):
        text, _ = validator.fix_commit("```\nfeat: 추가\n```")
        self.assertEqual(text, "feat: 추가")

    def test_bad_format_warns(self):
        _, warns = validator.fix_commit("그냥 제목")
        self.assertTrue(any("type" in w for w in warns))

    def test_preamble_removed(self):
        text, warns = validator.fix_commit("다음은 커밋 메시지입니다:\n\nfeat: 추가\n\n- a.py 수정")
        self.assertEqual(text, "feat: 추가\n\n- a.py 수정")
        self.assertTrue(any("설명 문장" in w for w in warns))


class PrTest(unittest.TestCase):
    def test_complete_pr_kept(self):
        raw = "TITLE: feat: 추가\n\n## Why\n- a\n\n## What\n- b\n\n## How to Test\n- c"
        title, body, warns = validator.fix_pr(raw)
        self.assertEqual(title, "feat: 추가")
        self.assertEqual(warns, [])
        for h in ("## Why", "## What", "## How to Test"):
            self.assertIn(h, body)

    def test_missing_section_and_bullet_fixed(self):
        title, body, warns = validator.fix_pr("TITLE: t\n## Why\n배경 설명\n## What\n")
        self.assertIn("- 배경 설명", body)
        self.assertIn("## How to Test\n" + validator.PLACEHOLDER, body)
        self.assertEqual(len(warns), 2)

    def test_title_limit(self):
        title, _, _ = validator.fix_pr("TITLE: " + "x" * 200)
        self.assertLessEqual(len(title), Format.PR_TITLE_MAX)


if __name__ == "__main__":
    unittest.main()
