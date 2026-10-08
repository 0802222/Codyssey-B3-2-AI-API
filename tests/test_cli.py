"""임시 git 저장소 + 로컬 모의 API 서버로 CLI 전체 흐름 검증."""
import contextlib
import io
import json
import os
import subprocess
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import main
from ai_commit_pr_generator import client
from ai_commit_pr_generator.config import API

RESPONSES = {}  # "next": (코드, 본문) 또는 순서대로 쓸 목록
LAST_BODY = {}
CALLS = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        LAST_BODY.update(body)
        CALLS.append(body)
        nxt = RESPONSES["next"]
        code, payload = nxt.pop(0) if isinstance(nxt, list) else nxt
        time.sleep(RESPONSES.get("delay", 0))
        data = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):
        pass


def ok(text, stop_reason="end_turn"):
    return 200, {"content": [{"type": "text", "text": text}], "stop_reason": stop_reason}


class CliTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/v1/messages"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

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
        CALLS.clear()
        self.old_delay = API.RETRY_DELAY_SEC
        API.RETRY_DELAY_SEC = 0  # 재시도 대기 없이 테스트
        # 개발자 PC의 실제 .env가 테스트에 섞이지 않도록 별도 경로로 교체 (git 저장소 밖)
        self.env_dir = tempfile.TemporaryDirectory()
        self.old_env_file = client.ENV_FILE
        client.ENV_FILE = Path(self.env_dir.name) / ".env"

    def tearDown(self):
        os.chdir(self.old_cwd)
        self.dir.cleanup()
        client.ENV_FILE = self.old_env_file
        self.env_dir.cleanup()
        API.RETRY_DELAY_SEC = self.old_delay
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

    def test_auth_error_not_retried(self):
        self.edit()
        RESPONSES["next"] = (401, {"error": {"message": "invalid x-api-key"}})
        code, out, err = self.run_cli("commit")
        self.assertEqual(code, 1)
        self.assertIn("HTTP 401", err)
        self.assertIn("[HINT]", err)
        self.assertEqual(len(CALLS), 1)  # 키가 틀리면 다시 보내도 실패하므로 재시도 안 함
        self.assertIn("호출 횟수: 1회", out)

    def test_server_error_retried_once_then_ok(self):
        self.edit()
        RESPONSES["next"] = [(529, {"error": {"message": "overloaded"}}), ok("feat: x")]
        code, out, _ = self.run_cli("commit")
        self.assertEqual(code, 0)
        self.assertIn("재시도", out)
        self.assertIn("호출 횟수: 2회", out)

    def test_retry_limited_to_one(self):
        self.edit()
        RESPONSES["next"] = (500, {"error": {"message": "boom"}})
        code, out, err = self.run_cli("commit")
        self.assertEqual(code, 1)
        self.assertEqual(len(CALLS), 1 + API.MAX_RETRIES)
        self.assertIn("호출 횟수: 2회", out)
        self.assertIn("서버 오류", err)

    def test_rate_limit_error(self):
        self.edit()
        RESPONSES["next"] = (429, {"error": {"message": "rate limited"}})
        code, _, err = self.run_cli("commit")
        self.assertEqual(code, 1)
        self.assertIn("HTTP 429", err)
        self.assertIn("요청 한도 초과", err)

    def test_network_error(self):
        self.edit()
        os.environ["AI_API_URL"] = "http://127.0.0.1:9/v1/messages"  # 닫혀 있는 포트
        code, _, err = self.run_cli("commit")
        self.assertEqual(code, 1)
        self.assertIn("네트워크 오류", err)

    def test_max_tokens_cut_off_warns(self):
        self.edit()
        RESPONSES["next"] = ok("TITLE: feat: x\n## Why\n- a", stop_reason="max_tokens")
        code, out, _ = self.run_cli("pr", "--max-tokens", "60")
        self.assertEqual(code, 0)
        self.assertIn("max_tokens(60) 상한에서 잘렸습니다", out)

    def test_timeout_option(self):
        self.edit()
        RESPONSES["next"], RESPONSES["delay"] = ok("feat: x"), 0.5
        try:
            code, _, err = self.run_cli("commit", "--timeout", "0.1")
        finally:
            RESPONSES["delay"] = 0
        self.assertEqual(code, 1)
        self.assertIn("응답 시간 초과 (0.1초)", err)
        self.assertIn("--timeout", err)

    def test_model_alias_sends_model_id(self):
        self.edit()
        RESPONSES["next"] = ok("feat: x")
        self.run_cli("commit", "--model", "sonnet")
        self.assertEqual(LAST_BODY["model"], "claude-sonnet-4")

    def test_unknown_model_rejected(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            main.main(["commit", "--model", "gpt-4"])
        self.assertEqual(CALLS, [])

    def test_models_command(self):
        code, out, _ = self.run_cli("models")
        self.assertEqual(code, 0)
        self.assertIn("haiku", out)
        self.assertIn("local", out)

    def test_local_model_needs_no_key(self):
        self.edit()
        del os.environ["AI_API_KEY"]
        RESPONSES["next"] = ok("feat: x")
        code, _, _ = self.run_cli("commit", "--model", "local")
        self.assertEqual(code, 0)

    def test_invalid_temperature(self):
        code, _, err = self.run_cli("commit", "--temperature", "1.5")
        self.assertEqual(code, 1)
        self.assertIn("--temperature", err)


if __name__ == "__main__":
    unittest.main()
