"""여러 모듈이 함께 쓰는 설정값. 값을 바꿀 때는 이 파일만 고치면 된다."""


class API:
    URL = "https://copa.codyssey.kr/v1/messages"
    VERSION = "2023-06-01"
    # 응답 대기 시간(초). urllib의 timeout은 '전체 시간'이 아니라 '소켓이 아무 데이터도 못 받은 시간' 기준
    # 비스트리밍 호출이라 응답은 생성이 끝난 뒤 한 번에 오므로, 사실상 '생성 완료까지 기다리는 시간'
    TIMEOUT_SEC = 60


class Defaults:
    MODEL = "claude-haiku-4"
    TEMPERATURE = 0.3
    MAX_TOKENS = 500


class SafeMode:
    MAX_FILES = 10
    MAX_LINES = 200


class Format:
    COMMIT_TITLE_RECOMMENDED = 50
    COMMIT_TITLE_MAX = 72
    PR_TITLE_MAX = 80

