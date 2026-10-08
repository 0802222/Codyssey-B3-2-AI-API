"""여러 모듈이 함께 쓰는 설정값. 값을 바꿀 때는 이 파일만 고치면 된다."""
from dataclasses import dataclass


class API:
    URL = "https://copa.codyssey.kr/v1/messages"
    VERSION = "2023-06-01"
    # 응답 대기 시간(초). urllib의 timeout은 '전체 시간'이 아니라 '소켓이 아무 데이터도 못 받은 시간' 기준
    # 비스트리밍 호출이라 응답은 생성이 끝난 뒤 한 번에 오므로, 사실상 '생성 완료까지 기다리는 시간'
    TIMEOUT_SEC = 60
    # 실패 시 재시도 횟수. 과제 권장(1회 실행당 1~2회 호출)에 맞춰 최대 1회만 재시도
    MAX_RETRIES = 1
    RETRY_DELAY_SEC = 2  # 서버가 Retry-After를 주면 그 값을 우선 (최대 RETRY_DELAY_MAX_SEC)
    RETRY_DELAY_MAX_SEC = 10
    # 일시적 오류라 다시 보내면 성공할 수 있는 HTTP 상태 코드 (529: Anthropic 서버 과부하)
    RETRYABLE_STATUS = (408, 429, 500, 502, 503, 504, 529)


class Defaults:
    MODEL = "haiku"  # MODELS의 키
    TEMPERATURE = 0.3
    MAX_TOKENS = 500


class SafeMode:
    MAX_FILES = 10
    MAX_LINES = 200


class Format:
    COMMIT_TITLE_RECOMMENDED = 50
    COMMIT_TITLE_MAX = 72
    PR_TITLE_MAX = 80


@dataclass(frozen=True)
class ModelProfile:
    id: str                    # API에 보내는 실제 모델명
    description: str
    url: str = API.URL
    timeout_sec: int = API.TIMEOUT_SEC
    needs_key: bool = True     # 로컬 서버는 API Key가 필요 없음


# --model 로 고를 수 있는 모델 목록 (python3 main.py models 로 확인)
MODELS = {
    "haiku": ModelProfile("claude-haiku-4", "빠르고 저렴함. 커밋/PR 요약에 충분"),
    "sonnet": ModelProfile("claude-sonnet-4", "더 정확하지만 느리고 비쌈. 변경이 크거나 복잡할 때"),
    # Ollama의 Anthropic 호환 API 사용. 모델 로딩·CPU/GPU 생성 속도 때문에 타임아웃을 길게 잡음
    "local": ModelProfile("qwen2.5-coder:7b", "로컬 LLM (Ollama). 코드가 외부로 나가지 않음",
                          url="http://localhost:11434/v1/messages", timeout_sec=300, needs_key=False),
}
