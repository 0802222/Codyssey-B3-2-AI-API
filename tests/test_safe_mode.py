import unittest

from ai_commit_pr_generator import safe_mode


class SafeModeTest(unittest.TestCase):
    def test_mask_key_and_email(self):
        text = "+API_KEY = 'abcdef123456'\n+key sk-ant-abcdefghijklmnopqrstuv\n+mail me@test.com"
        masked, n = safe_mode.mask(text)
        self.assertNotIn("abcdef123456", masked)
        self.assertNotIn("sk-ant", masked)
        self.assertNotIn("me@test.com", masked)
        self.assertGreaterEqual(n, 3)

    def test_common_secret_names_masked(self):
        for line in ('+GITHUB_TOKEN=abc123', '+SECRET_KEY = "xyz"', '+"password": "pw1234"'):
            masked, n = safe_mode.mask(line)
            self.assertIn("[MASKED]", masked, line)
            self.assertEqual(n, 1, line)

    def test_no_false_positive(self):
        for line in ("+DEFAULT_MAX_TOKENS = 500", "+    max_tokens=args.max_tokens,", "+icon = 'ui@2x.png'"):
            masked, n = safe_mode.mask(line)
            self.assertEqual((masked, n), (line, 0), line)

    def test_diff_marker_kept(self):
        masked, _ = safe_mode.mask("+admin@example.com")
        self.assertEqual(masked, "+[MASKED_EMAIL]")

    def test_limit_files(self):
        diff = "".join(f"diff --git a/f{i} b/f{i}\n+x\n" for i in range(15))
        out, truncated = safe_mode.limit_diff(diff, 10, 200)
        self.assertTrue(truncated)
        self.assertEqual(out.count("diff --git"), 10)

    def test_limit_lines(self):
        diff = "diff --git a/a b/a\n" + "+x\n" * 500
        out, truncated = safe_mode.limit_diff(diff, 10, 200)
        self.assertTrue(truncated)
        self.assertEqual(len(out.splitlines()), 200)

    def test_no_truncation_when_small(self):
        _, truncated = safe_mode.limit_diff("diff --git a/a b/a\n+x\n", 10, 200)
        self.assertFalse(truncated)


if __name__ == "__main__":
    unittest.main()
