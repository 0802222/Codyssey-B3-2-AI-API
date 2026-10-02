# AI Git 커밋/PR 자동 생성기

git 변경 사항(`git status`, `git diff`)을 AI API에 넘겨 커밋 메시지와 PR 초안을 만드는 CLI 도구.
생성 결과는 터미널에 출력만 함. push, PR 생성 같은 원격 반영은 하지 않음.

## 기능
- `commit`: 커밋 메시지 생성 (제목 1줄 + 선택 본문)
- `pr`: PR 제목 + 본문(Why / What / How to Test) 생성
- 모델, temperature, max_tokens를 CLI 옵션으로 변경
- 출력 검증: 길이·템플릿 규칙을 어기면 후처리로 보정하고 `[WARN]` 표시
- `--safe-mode`: 민감정보 마스킹 + diff 전송량 제한
- 명령 1회당 AI API 호출 1회, 호출 횟수 로그 출력

## 요구 사항
- Python 3.10 이상
- Git
- Anthropic API Key
- 외부 패키지 없음 (표준 라이브러리만 사용)

## 설치 및 실행
```bash
git clone <this-repo-url>
cd Codyssey-B3-2-AI-API
```
git이 초기화된 **대상 프로젝트의 루트**에서 실행함. (이 레포를 다른 프로젝트에 쓰려면 `python /path/to/main.py commit`)

## 환경변수(API Key) 설정
코드에 키를 넣지 않고 환경변수 `AI_API_KEY`로만 읽음.

```bash
# macOS / Linux
export AI_API_KEY="YOUR_KEY"

# Windows PowerShell
$env:AI_API_KEY="YOUR_KEY"
```

## 사용법
```bash
python main.py commit                       # 커밋 메시지 생성
python main.py pr                           # PR 제목/본문 생성
python main.py commit --safe-mode           # 마스킹 + diff 제한 후 전송
python main.py pr --model claude-sonnet-5-5 --temperature 0.2 --max-tokens 800
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--model` | `claude-haiku-4-5-20251001` | 사용할 모델 |
| `--temperature` | `0.3` | 0.0~1.0. 낮을수록 일관됨, 높을수록 다양함 |
| `--max-tokens` | `500` | 응답 최대 토큰. 너무 작으면 문장이 잘림 |
| `--safe-mode` | off | 마스킹 + diff 제한 활성화 |
| `--max-files` | `10` | safe-mode에서 전송할 최대 파일 수 |
| `--max-lines` | `200` | safe-mode에서 전송할 최대 diff 줄 수 |

## 출력 예시
아래는 참고용. 실제 문구는 매번 다름.

### 커밋 메시지
```
[INFO] Git status 수집 완료: 3개 파일 변경 감지
[INFO] Git diff 수집 완료: 128줄
[INFO] safe-mode OFF: diff 원문이 AI API로 전송됩니다. ...
[INFO] AI API 요청 중...
[INFO] AI API 호출 횟수: 1회
[DONE] 커밋 메시지 생성 완료

--- Commit Message ---
feat: git diff 기반 커밋 메시지 자동 생성 추가

- main.py, ai_gitgen/client.py: AI API 호출 로직 추가
- API Key 미설정 시 안내 메시지 출력
----------------------

※ 생성된 문구는 초안입니다. 검토 후 직접 적용하세요.
```

### PR 본문
```
--- PR Title ---
feat: 커밋/PR 자동 생성 기능 추가

--- PR Body ---
## Why
- 커밋/PR 설명 작성 시간을 줄이고 형식을 통일하기 위함

## What
- git status, git diff 수집 후 AI 입력으로 전달
- commit, pr 명령 구현 및 템플릿 적용

## How to Test
- export AI_API_KEY="YOUR_KEY"
- python main.py pr 실행 후 Why/What/How to Test 구조 확인
---------------
```

### 오류 / 변경 없음
```
[ERROR] AI_API_KEY 환경변수가 설정되지 않았습니다.
## 예) export AI_API_KEY="YOUR_KEY"
```
```
[INFO] 변경 사항이 없습니다. 커밋 메시지를 생성하지 않고 종료합니다.
```
API 오류는 원인을 함께 출력함. 예: `[ERROR] API 호출 실패 (HTTP 401): 인증 실패 (AI_API_KEY 확인)`

## 출력 규칙
| 항목 | 규칙 | 위반 시 |
|---|---|---|
| 커밋 제목 | 50자 권장, 최대 72자 | 50자 초과 경고, 72자 초과 자름 |
| 커밋 본문 | 불릿 1개 이상 (있을 때) | 불릿으로 변환 |
| PR 제목 | 최대 80자 | 자름 |
| PR 본문 | Why / What / How to Test 헤더 필수, 섹션별 불릿 1개 이상 | 헤더·불릿 보강 |

재생성 없이 후처리로 보정함 (API 호출 1회 유지).

## 주의사항
### 민감정보
`git diff`에 API Key, 비밀번호, 이메일 등이 있으면 외부 API로 전송됨. 민감정보가 있을 수 있으면 `--safe-mode` 사용.

- 마스킹: `api_key=...`, `password=...` 형태, `sk-...`/`ghp_...`/`AKIA...` 키, 이메일 → `[MASKED]`
- 제한: 최대 10개 파일, 200줄까지만 전송 (옵션으로 조정)
- 정규식 기반이라 모든 비밀을 잡지는 못함. `.env` 등은 애초에 커밋하지 않는 게 원칙.

### 비용 / 요청 제한
- 명령 1회 = API 1회 호출. 자동 재시도·재생성 없음
- 큰 diff는 토큰 비용 증가 → `--safe-mode`로 전송량 제한 권장
- 429(요청 한도 초과) 시 잠시 후 재실행
- 생성 문구는 최종 정답이 아님. 사용자가 검토 후 적용

## 테스트
```bash
python -m unittest discover -s tests -t .
```
임시 git 저장소와 로컬 모의 API 서버를 사용하므로 API Key 없이 실행 가능.

## 구조
```
main.py                 # CLI 진입점, 전체 흐름
ai_gitgen/git_utils.py  # git status/diff 수집
ai_gitgen/safe_mode.py  # 마스킹, diff 제한
ai_gitgen/prompts.py    # 프롬프트(커밋/PR)
ai_gitgen/client.py     # AI API REST 호출, 오류 처리
ai_gitgen/validator.py  # 길이/형식 검증, 후처리
tests/                  # 단위/통합 테스트
```
