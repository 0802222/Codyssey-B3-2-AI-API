"""임시 git 저장소 + 로컬 모의 API 서버로 CLI 전체 흐름 검증."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import main
from ai_commit_pr_generator import client

RESPONSES = {}
LAST_BODY = {}


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        LAST_BODY.update(body)
        code, payload = RESPONSES["next"]
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def ok(text):
    return 200, {"content": [{"type": "text", "text": text}]}


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1/messages"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.old_cwd = os.getcwd()
        os.chdir(self.dir.name)
        for cmd in (["init", "-q"], ["config", "user.email", "t@t.com"], ["config", "user.name", "t"]):
            subprocess.run(["git", *cmd], check=True)
        with open("a.txt", "w") as f:
            f.write("hello\n")
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-qm", "init"], check=True)
        os.environ["AI_API_URL"] = self.url
        os.environ["AI_API_KEY"] = "test-key"
        # 개발자 PC의 실제 .env가 테스트에 섞이지 않도록 별도 경로로 교체 (git 저장소 밖)
        self.env_dir = tempfile.TemporaryDirectory()
        self.old_env_file = client.ENV_FILE
        client.ENV_FILE = Path(self.env_dir.name) / ".env"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.dir.cleanup()
        client.ENV_FILE = self.old_env_file
        self.env_dir.cleanup()
        os.environ.pop("AI_API_URL", None)
        os.environ.pop("AI_API_KEY", None)

    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = main.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def edit(self, text="hello\nuser me@test.com\n"):
        with open("a.txt", "w") as f:
            f.write(text)

    def test_no_changes(self):
        code, out, _ = self.run_cli("commit")
        self.assertEqual(code, 0)
        self.assertIn("변경 사항이 없습니다", out)

    def test_missing_key(self):
        self.edit()
        del os.environ["AI_API_KEY"]
        code, _, err = self.run_cli("commit")
        self.assertEqual(code, 1)
        self.assertIn("AI_API_KEY", err)

    def test_key_from_env_file(self):
        del os.environ["AI_API_KEY"]
        client.ENV_FILE.write_text('# 주석\n\nexport AI_API_KEY="file-key"\n', encoding="utf-8")
        self.assertEqual(client.get_api_key(), "file-key")
        self.assertNotIn("AI_API_KEY", os.environ)  # 하위 프로세스로 전달되지 않음

    def test_env_var_overrides_env_file(self):
        client.ENV_FILE.write_text("AI_API_KEY=file-key\n", encoding="utf-8")
        self.assertEqual(client.get_api_key(), "test-key")

    def test_commit_ok(self):
        self.edit()
        RESPONSES["next"] = ok("feat: a.txt 수정\n\n- 내용 추가")
        code, out, _ = self.run_cli("commit", "--temperature", "0.1", "--max-tokens", "123")
        self.assertEqual(code, 0)
        self.assertIn("--- Commit Message ---", out)
        self.assertIn("feat: a.txt 수정", out)
        self.assertIn("호출 횟수: 1회", out)
        self.assertEqual(LAST_BODY["temperature"], 0.1)
        self.assertEqual(LAST_BODY["max_tokens"], 123)

    def test_pr_ok(self):
        self.edit()
        RESPONSES["next"] = ok("TITLE: feat: x\n## Why\n- a\n## What\n- b\n## How to Test\n- c")
        code, out, _ = self.run_cli("pr")
        self.assertEqual(code, 0)
        self.assertIn("--- PR Title ---", out)
        self.assertIn("## How to Test", out)

    def test_safe_mode_masks_email(self):
        self.edit()
        RESPONSES["next"] = ok("feat: x")
        self.run_cli("commit", "--safe-mode")
        self.assertNotIn("me@test.com", json.dumps(LAST_BODY))
        self.run_cli("commit")
        self.assertIn("me@test.com", json.dumps(LAST_BODY))

    def test_auth_error(self):
        self.edit()
        RESPONSES["next"] = (401, {"error": {"message": "invalid x-api-key"}})
        code, _, err = self.run_cli("commit")
        self.assertEqual(code, 1)
        self.assertIn("HTTP 401", err)


if __name__ == "__main__":
    unittest.main()
