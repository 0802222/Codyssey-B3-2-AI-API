"""git status / git diff 수집. 조회 명령만 사용한다."""
import subprocess


class GitError(Exception):
    pass


def _run(args: list[str]) -> str:
    try:
        result = subprocess.run(
            ["git", *args], capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except FileNotFoundError:
        raise GitError("git 명령을 찾을 수 없습니다. git 설치를 확인하세요.")
    if result.returncode != 0:
        raise GitError(result.stderr.strip() or f"git {' '.join(args)} 실패")
    return result.stdout


def ensure_repo() -> None:
    try:
        _run(["rev-parse", "--is-inside-work-tree"])
    except GitError:
        raise GitError("Git 저장소가 아닙니다. 프로젝트 루트(git init 된 곳)에서 실행하세요.")


def get_status() -> str:
    return _run(["status", "--short"]).strip()


def get_diff() -> str:
    """staged + unstaged 변경을 합쳐서 반환. 커밋이 없는 저장소도 처리한다."""
    try:
        return _run(["diff", "HEAD"])
    except GitError:
        return _run(["diff", "--cached"]) + _run(["diff"])


def get_branch() -> str:
    try:
        return _run(["branch", "--show-current"]).strip() or "(detached HEAD)"
    except GitError:
        return "(unknown)"
