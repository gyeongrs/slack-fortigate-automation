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

## FortiGate 없이 테스트 (dry-run)

실물 장비가 없어도 전체 플로우를 끝까지 테스트할 수 있습니다.
`FORTIGATE_DRY_RUN=true`이면 장비에 HTTP 호출을 하지 않고, 현재 상태를
"비어 있음"으로 간주해 모든 객체를 생성 대상으로 보고, apply는 "무엇을
적용할지"만 로그로 출력하고 성공 처리합니다.

- **로컬**: `.env`에 `FORTIGATE_DRY_RUN=true` (이미 기본값) → `fwctl plan` / `fwctl apply --yes`
- **CI**: 저장소 `Settings → Secrets and variables → Actions → Variables`에서
  변수 `FORTIGATE_DRY_RUN=true` 추가 → `apply.yml`이 장비/시크릿 없이 성공

실제 장비를 붙일 때는 `FORTIGATE_DRY_RUN=false`로 바꾸고 아래를 설정하세요.

## FortiGate 준비

1. `System > Administrators > Create New > REST API Admin`
2. 최소 권한 프로파일 부여(방화벽 정책/주소/서비스 쓰기만)
3. **Trusted Hosts** 로 CI/봇 IP만 허용
4. 생성된 API 토큰을 `FORTIGATE_API_TOKEN` 에 설정

## Slack 앱 준비

1. Slash Command `/fw-request`
2. Interactivity 활성화 (버튼 동작에 필요)
3. Bot Scopes: `commands`, `chat:write`
4. 실행 방식 선택:

**A. Socket Mode (권장, 사내망)** — 인바운드 포트 불필요
- Basic Information → App-Level Tokens 에서 `connections:write` 스코프 토큰 생성 → `SLACK_APP_TOKEN`
- Socket Mode 토글 ON
- 실행: `python -m slack_bot.app`

**B. HTTP Mode** — 공개 HTTPS 필요
- Slash Command / Interactivity Request URL → `https://<host>/slack/events`
- 실행: `uvicorn slack_bot.app:api --port 3000`

### 모바일 승인 플로우
`/fw-request` 제출 → 봇이 **PR 생성 + 승인/거부 버튼 메시지** 게시 →
**요청자가 아닌 다른 사람**이 폰에서 `Approve & merge` 탭 → PR 머지(→ CI apply),
`Reject` 탭 → PR close. 기본적으로 요청자 본인이 승인하면 차단됩니다(ephemeral 경고).
혼자 테스트하거나 1인 운영이면 `.env`에 `ALLOW_SELF_APPROVE=true`로 자기승인을
허용할 수 있습니다(운영에서는 `false` 권장).
> 버튼 승인이 PR을 머지하므로, `production` environment 승인까지 두면 2단계 게이트가 됩니다.

## GitHub 준비

- Repo Secrets: `FORTIGATE_HOST`, `FORTIGATE_API_TOKEN`, `FORTIGATE_VERIFY_TLS`
- `production` Environment에 **필수 리뷰어**를 지정해 apply를 한 번 더 게이트
- `main` 브랜치 보호 규칙: PR 필수 + `validate` 체크 통과 필수

## 안전 설계 요약

- **요청자 ≠ 승인자**: PR 리뷰 + production environment 승인
- **가드레일**: `any-any` 금지, 금지 포트, 허용 인터페이스, 필수 로깅/스케줄
- **참조 정합성**: 정책이 참조하는 주소/서비스가 정의돼 있지 않으면 거부(장비 적용 실패 예방), 내장 서비스는 `allowed_builtin_services` 화이트리스트로 허용
- **중복 방지**: 주소/서비스/정책 이름 중복 검출(이름이 매칭 키라 덮어쓰기 사고 예방)
- **트립와이어**: `max_changes_per_apply` 초과 시 apply 거부
- **관리 태그**: 엔진은 `managed-by:fwgitops` 객체만 생성/수정, 수동 객체는 보존
- **삭제 안 함**: YAML에서 빠진 객체를 자동 삭제하지 않음(사고 방지)
- **감사/롤백**: git 히스토리 = 변경 이력, `revert` 로 롤백

