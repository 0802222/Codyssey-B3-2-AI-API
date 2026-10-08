"""AI 출력 검증 + 후처리(재생성 없이 규칙에 맞게 다듬기). 변경 내역은 경고 목록으로 반환."""
import re

COMMIT_TITLE_RECOMMENDED = 50
COMMIT_TITLE_MAX = 72
PR_TITLE_MAX = 80
SECTIONS = ["Why", "What", "How to Test"]
PLACEHOLDER = "- (내용 보완 필요)"
TITLE_PATTERN = re.compile(r"^[A-Za-z]+(\([^)]*\))?!?: ")  # feat: / fix(api): / feat!:


def _strip_fence(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```\w*\n", "", text)
    return re.sub(r"\n```$", "", text).strip()


def _truncate(title: str, limit: int) -> str:
    return title if len(title) <= limit else title[: limit - 1].rstrip() + "…"


def _ensure_bullets(lines: list[str]) -> list[str]:
    """불릿이 하나도 없으면 비어있지 않은 줄을 불릿으로 바꾼다."""
    lines = [l for l in lines if l.strip()]
    if any(l.lstrip().startswith(("- ", "* ")) for l in lines):
        return lines
    return [f"- {l.strip()}" for l in lines] or [PLACEHOLDER]


def fix_commit(text: str) -> tuple[str, list[str]]:
    warnings = []
    lines = _strip_fence(text).splitlines()
    # "다음은 커밋 메시지입니다:" 같은 앞 문장은 버리고 `type: 제목` 형식의 첫 줄부터 사용
    start = next((i for i, l in enumerate(lines) if TITLE_PATTERN.match(l.strip())), None)
    if start is None:
        warnings.append("커밋 제목이 `type: 제목` 형식이 아닙니다.")
        start = 0
    elif start > 0:
        warnings.append("제목 앞의 설명 문장을 제거했습니다.")
    title = lines[start].strip() if lines else ""
    body = [l for l in lines[start + 1:] if l.strip()]
    if len(title) > COMMIT_TITLE_MAX:
        title = _truncate(title, COMMIT_TITLE_MAX)
        warnings.append(f"커밋 제목이 {COMMIT_TITLE_MAX}자를 넘어 잘랐습니다.")
    elif len(title) > COMMIT_TITLE_RECOMMENDED:
        warnings.append(f"커밋 제목이 권장 길이({COMMIT_TITLE_RECOMMENDED}자)를 넘습니다.")
    result = title
    if body:
        result += "\n\n" + "\n".join(_ensure_bullets(body))
    return result, warnings


def fix_pr(text: str) -> tuple[str, str, list[str]]:
    """(제목, 본문, 경고) 반환."""
    warnings = []
    text = _strip_fence(text)
    title = ""
    sections: dict[str, list[str]] = {}
    current = None
    for line in text.splitlines():
        m_title = re.match(r"(?i)^TITLE:\s*(.*)$", line.strip())
        m_head = re.match(r"^#{1,6}\s*(Why|What|How to Test)\b", line.strip(), re.I)
        if m_title and not title:
            title = m_title.group(1).strip()
        elif m_head:
            current = next(s for s in SECTIONS if s.lower() == m_head.group(1).lower())
            sections.setdefault(current, [])
        elif current:
            sections[current].append(line)
    if not title:
        title = "PR 제목 없음"
        warnings.append("PR 제목을 찾지 못해 기본값을 넣었습니다.")
    if len(title) > PR_TITLE_MAX:
        title = _truncate(title, PR_TITLE_MAX)
        warnings.append(f"PR 제목이 {PR_TITLE_MAX}자를 넘어 잘랐습니다.")
    parts = []
    for name in SECTIONS:
        if name not in sections:
            warnings.append(f"## {name} 섹션이 없어 추가했습니다.")
        elif not any(l.strip() for l in sections[name]):
            warnings.append(f"## {name} 섹션이 비어 있어 보완했습니다.")
        body = _ensure_bullets(sections.get(name, []))
        parts.append(f"## {name}\n" + "\n".join(body))
    return title, "\n\n".join(parts), warnings
