"""AI 기반 Git 커밋 메시지 / PR 초안 생성기 (CLI).

사용: python main.py commit | pr | models [옵션]
"""
import argparse
import sys

# 아래 모듈은 3.10 문법(X | None 등)을 써서 import 단계에서 TypeError가 나므로 먼저 확인
if sys.version_info < (3, 10):
    sys.exit(f"[ERROR] Python 3.10 이상이 필요합니다. (현재 {sys.version.split()[0]})")

from ai_commit_pr_generator import client, git_utils, prompts, safe_mode, validator
from ai_commit_pr_generator.config import Defaults, MODELS, SafeMode


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="git 변경 사항으로 커밋 메시지/PR 초안을 생성합니다.")
    p.add_argument("command", choices=["commit", "pr", "models"],
                   help="commit: 커밋 메시지, pr: PR 제목/본문, models: 모델 목록")
    p.add_argument("--model", choices=list(MODELS), default=Defaults.MODEL,
                   help="사용할 모델 (기본: %(default)s, 목록: python3 main.py models)")
    p.add_argument("--temperature", type=float, default=Defaults.TEMPERATURE,
                   help="무작위성 0.0~1.0 (기본: %(default)s)")
    p.add_argument("--max-tokens", type=int, default=Defaults.MAX_TOKENS,
                   help="최대 출력 토큰 (기본: %(default)s)")
    p.add_argument("--timeout", type=float,
                   help="응답 대기 시간(초) (기본: 모델별 값, python3 main.py models로 확인)")
    p.add_argument("--safe-mode", action="store_true", help="민감정보 마스킹 + diff 전송량 제한")
    p.add_argument("--max-files", type=int, default=SafeMode.MAX_FILES,
                   help="safe-mode 최대 파일 수 (기본: %(default)s)")
    p.add_argument("--max-lines", type=int, default=SafeMode.MAX_LINES,
                   help="safe-mode 최대 diff 줄 수 (기본: %(default)s)")
    return p


def info(msg: str) -> None:
    print(f"[INFO] {msg}")


def error(msg: str) -> int:
    print(f"[ERROR] {msg}", file=sys.stderr)
    return 1


def print_models() -> int:
    print("사용 가능한 모델 (--model <이름>)\n")
    for name, m in MODELS.items():
        mark = " (기본)" if name == Defaults.MODEL else ""
        print(f"  {name:<8} {m.id:<20} 타임아웃 {m.timeout_sec}초  {m.description}{mark}")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "models":
        return print_models()
    if not 0.0 <= args.temperature <= 1.0:
        return error("--temperature는 0.0~1.0 범위여야 합니다.")
    if args.max_tokens < 1 or args.max_files < 1 or args.max_lines < 1:
        return error("--max-tokens, --max-files, --max-lines는 1 이상이어야 합니다.")
    if args.timeout is not None and args.timeout <= 0:
        return error("--timeout은 0보다 커야 합니다.")
    profile = MODELS[args.model]

    # 1. Git 변경 사항 수집
    try:
        git_utils.ensure_repo()
        status = git_utils.get_status()
        if not status:
            info("변경 사항이 없습니다. 커밋 메시지를 생성하지 않고 종료합니다."
                 if args.command == "commit" else
                 "변경 사항이 없습니다. PR 초안을 생성하지 않고 종료합니다.")
            return 0
        diff = git_utils.get_diff()
        branch = git_utils.get_branch()
    except git_utils.GitError as e:
        return error(str(e))
    info(f"Git status 수집 완료: {len(status.splitlines())}개 파일 변경 감지")
    info(f"Git diff 수집 완료: {len(diff.splitlines())}줄")
    if args.command == "pr":
        info(f"현재 브랜치: {branch}")

    # 2. 안전 모드
    if args.safe_mode:
        diff, stat = safe_mode.apply_safe_mode(diff, args.max_files, args.max_lines)
        status, status_masked = safe_mode.mask(status)
        info(f"safe-mode: 민감정보 {stat['masked'] + status_masked}건 마스킹"
             + (f", diff 제한 적용(최대 {args.max_files}파일/{args.max_lines}줄)" if stat["truncated"] else ""))
    else:
        info("safe-mode OFF: diff 원문이 AI API로 전송됩니다. 민감정보가 있다면 --safe-mode를 사용하세요.")

    # 3. AI API 호출 (명령당 1회, 일시적 오류일 때만 1회 재시도)
    try:
        api_key = client.get_api_key() if profile.needs_key else ""
        info(f"AI API 요청 중... (모델: {profile.id})")
        system = prompts.COMMIT_SYSTEM if args.command == "commit" else prompts.PR_SYSTEM
        result = client.generate(system, prompts.build_user_prompt(branch, status, diff), api_key,
                                 profile, args.temperature, args.max_tokens, args.timeout,
                                 on_retry=lambda msg: print(f"[WARN] {msg}"))
    except client.AIClientError as e:
        if e.attempts:
            info(f"AI API 호출 횟수: {e.attempts}회")
        return error(str(e) + (f"\n[HINT] {e.hint}" if e.hint else ""))
    info(f"AI API 호출 횟수: {result.attempts}회")
    raw = result.text

    # 4. 검증/다듬기 후 출력
    if args.command == "commit":
        message, warnings = validator.fix_commit(raw)
        print("[DONE] 커밋 메시지 생성 완료\n")
        print("--- Commit Message ---")
        print(message)
        print("----------------------")
    else:
        title, body, warnings = validator.fix_pr(raw)
        print("[DONE] PR 초안 생성 완료\n")
        print("--- PR Title ---")
        print(title)
        print("\n--- PR Body ---")
        print(body)
        print("---------------")
    if result.cut_off:
        warnings.insert(0, f"응답이 max_tokens({args.max_tokens}) 상한에서 잘렸습니다. --max-tokens를 늘려 보세요.")
    for w in warnings:
        print(f"[WARN] {w}")
    print("\n※ 생성된 문구는 초안입니다. 검토 후 직접 적용하세요.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
