# slack-fortigate-automation

Slack 요청을 받아 **GitOps 방식**으로 FortiGate 방화벽 정책을 자동화합니다.
방화벽을 직접 건드리지 않고, 모든 변경을 **PR(승인 게이트 + 감사 로그)** 로 만들고
머지되면 CI가 FortiGate REST API로 적용합니다.

```
/fw-request (Slack 모달)
   → 봇이 정책을 YAML로 커밋 + PR 자동 생성
   → CI 검증(any-any 금지 / 포트 화이트리스트) + plan diff 표시
   → 담당자 승인 & merge
   → CI가 FortiGate REST API로 apply   (감사·롤백은 git이 담당)
```

## 구성요소

| 경로 | 역할 |
|------|------|
| `policies/*.yaml` | 방화벽의 **목표 상태**(desired state). 주소객체 · 서비스 · 정책 |
| `config/policy_rules.yaml` | 안전 가드레일(any 금지, 금지 포트, 허용 인터페이스, 변경 트립와이어) |
| `src/fwgitops/` | 엔진: REST 클라이언트 · 검증기 · plan(diff) · apply · `fwctl` CLI |
| `slack_bot/` | Slack `/fw-request` 모달 → GitHub PR 자동 생성 |
| `.github/workflows/` | `validate`(PR마다 검증/dry-run), `apply`(머지 시 적용) |

## 사전 준비 (이 PC)

현재 환경에는 **Git과 Python이 설치돼 있지 않습니다.** 다음을 설치하세요.

- [Python 3.11+](https://www.python.org/downloads/windows/) (설치 시 "Add to PATH" 체크)
- [Git for Windows](https://git-scm.com/download/win)

> 참고: `C:\...\WindowsApps\python.exe` 는 Microsoft Store 별칭 스텁이라 실제 실행이 안 됩니다.
> 설치 관리자로 정식 Python을 설치하세요.

## 로컬 사용법

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[bot,dev]"

copy .env.example .env   # 값 채우기

fwctl validate           # 오프라인: 가드레일 검증
fwctl plan               # 온라인: 장비와 diff (변경 안 함)
fwctl apply              # 온라인: 가드레일+트립와이어 통과 후 적용
pytest                   # 검증기 테스트
```

## FortiGate 준비

1. `System > Administrators > Create New > REST API Admin`
2. 최소 권한 프로파일 부여(방화벽 정책/주소/서비스 쓰기만)
3. **Trusted Hosts** 로 CI/봇 IP만 허용
4. 생성된 API 토큰을 `FORTIGATE_API_TOKEN` 에 설정

## Slack 앱 준비

1. Slash Command `/fw-request` → Request URL `https://<host>/slack/events`
2. Interactivity → 동일 URL
3. Bot Scopes: `commands`, `chat:write`
4. 봇 실행: `uvicorn slack_bot.app:api --port 3000`

## GitHub 준비

- Repo Secrets: `FORTIGATE_HOST`, `FORTIGATE_API_TOKEN`, `FORTIGATE_VERIFY_TLS`
- `production` Environment에 **필수 리뷰어**를 지정해 apply를 한 번 더 게이트
- `main` 브랜치 보호 규칙: PR 필수 + `validate` 체크 통과 필수

## 안전 설계 요약

- **요청자 ≠ 승인자**: PR 리뷰 + production environment 승인
- **가드레일**: `any-any` 금지, 금지 포트, 허용 인터페이스, 필수 로깅/스케줄
- **트립와이어**: `max_changes_per_apply` 초과 시 apply 거부
- **관리 태그**: 엔진은 `managed-by:fwgitops` 객체만 생성/수정, 수동 객체는 보존
- **삭제 안 함**: YAML에서 빠진 객체를 자동 삭제하지 않음(사고 방지)
- **감사/롤백**: git 히스토리 = 변경 이력, `revert` 로 롤백

