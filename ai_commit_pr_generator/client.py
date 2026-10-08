"""Anthropic Messages API REST 호출 (표준 라이브러리 urllib)."""
import json
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from .config import API, Defaults, MODELS, ModelProfile

# 대상 프로젝트가 아니라 이 도구 폴더(main.py 옆)의 .env를 읽음
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


# AIClientError : AI API 호출 실패를 나타내는 예외 클래스
class AIClientError(Exception):
    # 예외의 발생과 처리를 다른 코드위치에서 담당하도록 분리하기 위해 정의
    # rasie: 호출자에게 예외를 전달
    # except: 호출자는 적절한 메시지를 출력하고 종료코드 반환
    def __init__(self, message: str, hint: str = "", retryable: bool = False,
                 retry_after: float | None = None):
        super().__init__(message)
        self.hint = hint                # 사용자가 다음에 할 일
        self.retryable = retryable      # 다시 보내면 성공할 수 있는 일시적 오류인지
        self.retry_after = retry_after  # 서버가 알려준 대기 시간(초)
        self.attempts = 0               # 실패까지 보낸 요청 수


@dataclass
class Result:
    text: str
    cut_off: bool   # max_tokens 상한에서 잘렸는지
    attempts: int   # 실제로 보낸 요청 수 (재시도 포함)


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


def generate(system: str, user: str, api_key: str, profile: ModelProfile = MODELS[Defaults.MODEL],
             temperature: float = Defaults.TEMPERATURE, max_tokens: int = Defaults.MAX_TOKENS,
             timeout: float | None = None, on_retry: Callable[[str], None] | None = None) -> Result:
    """요청 구성 -> 전송(일시적 오류면 1회 재시도) -> 응답 파싱.
    실패는 원인과 다음 행동을 담은 AIClientError로 변환."""
    payload = {
        "model": profile.id,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    request = urllib.request.Request(
        os.environ.get("AI_API_URL", profile.url),  # 환경변수로 엔드포인트 변경 가능
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": API.VERSION,
        },
        method="POST",
    )
    timeout = timeout or profile.timeout_sec

    for attempt in range(1, API.MAX_RETRIES + 2):
        try:
            body = _send(request, timeout, profile)
            break
        except AIClientError as e:
            e.attempts = attempt
            if not e.retryable or attempt > API.MAX_RETRIES:
                raise
            delay = min(e.retry_after or API.RETRY_DELAY_SEC, API.RETRY_DELAY_MAX_SEC)
            if on_retry:
                on_retry(f"{e} -> {delay:g}초 후 재시도 ({attempt + 1}/{API.MAX_RETRIES + 1})")
            time.sleep(delay)

    text = "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")
    if not text.strip():
        raise AIClientError("AI 응답에 텍스트가 없습니다.", "--max-tokens를 늘리거나 다시 실행하세요.")
    # stop_reason이 "max_tokens"면 응답이 길이 상한에서 잘린 것
    return Result(text.strip(), body.get("stop_reason") == "max_tokens", attempt)


def _send(request: urllib.request.Request, timeout: float, profile: ModelProfile) -> dict:
    """요청 1회. 실패 원인별로 재시도 가능 여부를 나눠 AIClientError로 변환."""
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise _http_error(e) from None
    except TimeoutError:
        raise _timeout_error(timeout) from None
    except urllib.error.URLError as e:
        if isinstance(e.reason, TimeoutError):
            raise _timeout_error(timeout) from None
        hint = ("로컬 LLM 서버가 실행 중인지 확인하세요. (예: ollama serve)" if not profile.needs_key
                else "인터넷 연결과 AI_API_URL 주소를 확인하세요.")
        raise AIClientError(f"네트워크 오류: {e.reason}", hint, retryable=True) from None
    except json.JSONDecodeError:
        raise AIClientError("응답을 JSON으로 해석할 수 없습니다.", "AI_API_URL이 AI API 주소가 맞는지 확인하세요.") from None


def _timeout_error(timeout: float) -> AIClientError:
    return AIClientError(f"응답 시간 초과 ({timeout:g}초)",
                         "--timeout을 늘리거나 --safe-mode로 보내는 diff 양을 줄이세요.", retryable=True)


# HTTP 상태 코드별 (원인, 사용자가 할 일)
HTTP_HINTS = {
    400: ("요청 형식 오류", "--max-tokens 값이나 모델 설정을 확인하세요."),
    401: ("인증 실패", ".env 또는 환경변수의 AI_API_KEY를 확인하세요."),
    403: ("권한 없음", "이 키로 해당 모델을 쓸 수 있는지 확인하세요."),
    404: ("모델 또는 엔드포인트를 찾을 수 없음", "python3 main.py models 로 모델 목록을 확인하세요."),
    429: ("요청 한도 초과", "잠시 후 다시 실행하세요."),
}


def _http_error(e: urllib.error.HTTPError) -> AIClientError:
    detail = ""
    try:
        detail = json.loads(e.read().decode("utf-8")).get("error", {}).get("message", "")
    except Exception:
        pass
    if e.code in HTTP_HINTS:
        reason, hint = HTTP_HINTS[e.code]
    elif e.code >= 500:
        reason, hint = "서버 오류", "잠시 후 다시 실행하거나 --model로 다른 모델을 선택하세요."
    else:
        reason, hint = "API 오류", ""
    message = f"API 호출 실패 (HTTP {e.code}): {reason}" + (f" - {detail}" if detail else "")
    return AIClientError(message, hint, retryable=e.code in API.RETRYABLE_STATUS,
                         retry_after=_retry_after(e))


def _retry_after(e: urllib.error.HTTPError) -> float | None:
    try:
        return float(e.headers.get("retry-after", ""))
    except (TypeError, ValueError):
        return None
