"""Anthropic Messages API REST 호출 (표준 라이브러리 urllib)."""
import json
import os
import socket
import urllib.error
import urllib.request
from pathlib import Path

API_URL = "https://copa.codyssey.kr/v1/messages"
API_VERSION = "2023-06-01"
TIMEOUT_SEC = 60

DEFAULT_MODEL = "claude-haiku-4"
DEFAULT_TEMPERATURE = 0.3
DEFAULT_MAX_TOKENS = 500

# 대상 프로젝트가 아니라 이 도구 폴더(main.py 옆)의 .env를 읽음
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class AIClientError(Exception):
    pass


def get_api_key() -> str:
    """환경변수 우선, 없으면 .env. os.environ에 넣지 않아 git 하위 프로세스로 전달되지 않음."""
    key = os.environ.get("AI_API_KEY", "").strip() or _read_env_file().get("AI_API_KEY", "").strip()
    if not key:
        raise AIClientError(f"AI_API_KEY가 설정되지 않았습니다.\n## 예) {ENV_FILE} 파일에 AI_API_KEY=YOUR_KEY 작성")
    return key


def _read_env_file() -> dict[str, str]:
    """KEY=VALUE 형식만 지원. 빈 줄·# 주석·export 접두어·감싼 따옴표 처리."""
    try:
        lines = ENV_FILE.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return {}
    values = {}
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.removeprefix("export ").split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[name.strip()] = value
    return values


def generate(system: str, user: str, api_key: str, model: str = DEFAULT_MODEL,
             temperature: float = DEFAULT_TEMPERATURE, max_tokens: int = DEFAULT_MAX_TOKENS) -> str:
    """요청 구성 -> 전송 -> 응답 파싱. 실패는 원인을 담은 AIClientError로 변환."""
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    request = urllib.request.Request(
        os.environ.get("AI_API_URL", API_URL),  # 환경변수로 엔드포인트 변경 가능
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API_VERSION,
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SEC) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise AIClientError(_http_message(e)) from None
    except (urllib.error.URLError, socket.timeout, TimeoutError) as e:
        reason = getattr(e, "reason", e)
        raise AIClientError(f"네트워크 오류: {reason}") from None
    except json.JSONDecodeError:
        raise AIClientError("응답을 JSON으로 해석할 수 없습니다.") from None

    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    if not text.strip():
        raise AIClientError("AI 응답에 텍스트가 없습니다.")
    return text.strip()


def _http_message(e: urllib.error.HTTPError) -> str:
    detail = ""
    try:
        detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
    except Exception:
        pass
    hints = {
        400: "요청 형식 오류 (모델명/파라미터 확인)",
        401: "인증 실패 (AI_API_KEY 확인)",
        403: "권한 없음",
        404: "모델 또는 엔드포인트를 찾을 수 없음 (모델명 확인)",
        429: "요청 한도 초과 (잠시 후 재시도)",
    }
    hint = hints.get(e.code, "서버 오류" if e.code >= 500 else "API 오류")
    return f"API 호출 실패 (HTTP {e.code}): {hint}" + (f" - {detail}" if detail else "")
