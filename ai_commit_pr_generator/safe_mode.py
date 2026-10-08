"""민감정보 마스킹 + diff 전송량 제한."""
import re

from .config import SafeMode

# (이름, 정규식, 치환 문자열)
# - secret-assign: 이름이 키워드로 끝나야 함 (GITHUB_TOKEN=, secret_key= 는 잡고 max_tokens= 는 제외)
# - email: 앞에 diff의 `+`가 붙어도 마커는 남기고, ui@2x.png 같은 이미지 파일명은 제외
MASK_RULES = [
    ("secret-assign", re.compile(r"(?i)((?:api[_-]?key|secret(?:[_-]?key)?|token|passwd|password)['\"]?\s*[:=]\s*)['\"]?[^\s'\"]+['\"]?"), r"\1[MASKED]"),
    ("api-key", re.compile(r"\b(?:sk|pk|ghp|gho|xox[abp])[-_][A-Za-z0-9_\-]{16,}"), "[MASKED_KEY]"),
    ("aws-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "[MASKED_KEY]"),
    ("email", re.compile(r"(?<![\w.-])\w[\w.+-]*@[\w-]+(?:\.[\w-]+)*\.(?!(?:png|jpe?g|gif|svg|webp)\b)[A-Za-z]{2,}\b"), "[MASKED_EMAIL]"),
]


def mask(text: str) -> tuple[str, int]:
    """패턴에 걸린 값을 가리고 (결과, 마스킹 횟수)를 반환."""
    total = 0
    for _, pattern, repl in MASK_RULES:
        text, n = pattern.subn(repl, text)
        total += n
    return text, total


def limit_diff(diff: str, max_files: int, max_lines: int) -> tuple[str, bool]:
    """파일 수/줄 수 제한. 잘렸으면 True."""
    blocks = re.split(r"(?m)^(?=diff --git )", diff)
    blocks = [b for b in blocks if b]
    truncated = len(blocks) > max_files
    lines = "".join(blocks[:max_files]).splitlines()
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        truncated = True
    return "\n".join(lines), truncated


def apply_safe_mode(diff: str, max_files: int = SafeMode.MAX_FILES,
                    max_lines: int = SafeMode.MAX_LINES) -> tuple[str, dict]:
    limited, truncated = limit_diff(diff, max_files, max_lines)
    masked, count = mask(limited)
    return masked, {"masked": count, "truncated": truncated}
