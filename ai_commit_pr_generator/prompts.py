"""프롬프트 구성. 역할 / 형식 / 길이 규칙은 system, 변경 맥락은 user에 둔다."""
from .config import Format

COMMIT_SYSTEM = f"""당신은 git 커밋 메시지를 작성하는 도우미입니다.
규칙:
- 첫 줄: `type: 제목` 형식 (type은 feat, fix, docs, refactor, test, chore 중 하나), {Format.COMMIT_TITLE_RECOMMENDED}자 이내, 마침표 없음
- 제목 아래 빈 줄 한 줄, 이어서 본문 작성
- 본문: 변경된 파일(또는 모듈) 1~3개 언급, 핵심 변경 1~2개를 `- ` 불릿으로 요약
- 한국어로 작성하고, diff에 없는 내용은 추측하지 않음
- 설명, 코드블록, 인사말 없이 커밋 메시지만 출력"""

PR_SYSTEM = f"""당신은 Pull Request 초안을 작성하는 도우미입니다.
출력 형식(정확히 지킬 것):
TITLE: <PR 제목 한 줄, {Format.PR_TITLE_MAX}자 이내>

## Why
- 변경 배경 (불릿 1개 이상)

## What
- 핵심 변경 사항 (불릿 1개 이상)

## How to Test
- 테스트 방법 (불릿 1개 이상)

규칙:
- 한국어로 작성하고, diff에 없는 내용은 추측하지 않음
- 위 형식 외의 설명, 코드블록, 인사말은 출력하지 않음"""


def build_user_prompt(branch: str, status: str, diff: str) -> str:
    return (
        f"현재 브랜치: {branch}\n\n"
        f"[git status --short]\n{status}\n\n"
        f"[git diff]\n{diff if diff.strip() else '(diff 없음: untracked 파일만 있을 수 있음)'}"
    )
