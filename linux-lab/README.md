# Linux 실전 교육 랩

운영(Ops) 현장에서 자주 마주치는 이슈를 **시나리오 기반**으로 연습하는 환경입니다.
Take Control 없이 **Terminal 탭**에서 바로 시작할 수 있습니다.

## 빠른 시작

```bash
cd /workspace/linux-lab
./setup.sh          # 실습 환경 초기화 (장애 상태 생성)
./check.sh          # 전체 시나리오 점검 (해결 전/후)
./check.sh 03       # 특정 시나리오만 점검
```

## 학습 로드맵

| # | 시나리오 | 실무 이슈 | 핵심 명령 |
|---|---------|----------|----------|
| 01 | [로그 분석 장애](scenarios/01-log-incident/TASKS.md) | 500 에러 급증, 공격 IP 추적 | `grep`, `awk`, `sort`, `uniq` |
| 02 | [권한 문제](scenarios/02-permissions/TASKS.md) | 스크립트 실행 불가, 설정 노출 | `chmod`, `chown`, `ls -l` |
| 03 | [디스크 부족](scenarios/03-disk-full/TASKS.md) | 로그로 디스크 Full | `du`, `find`, `gzip`, `df` |
| 04 | [프로세스 장애](scenarios/04-process-incident/TASKS.md) | CPU 100% 프로세스 | `ps`, `top`, `kill` |
| 05 | [cron 백업 실패](scenarios/05-cron-failure/TASKS.md) | 백업 미실행 | `crontab`, `grep`, 로그 분석 |
| 06 | [서비스 연결 실패](scenarios/06-service-down/TASKS.md) | DB 연결 불가 | `ss`, `curl`, 설정 파일 |

## 권장 학습 순서

```
1일차: 01 로그 분석  →  grep/awk 파이프라인
2일차: 02 권한       →  chmod/chown
3일차: 03 디스크     →  du/find/df
4일차: 04 프로세스   →  ps/kill
5일차: 05 cron       →  스케줄·백업
6일차: 06 서비스     →  포트·설정·연결
```

## 실습 방법

1. `scenarios/XX-*/TASKS.md` 를 읽고 **증상**을 파악합니다.
2. Linux 명령으로 **원인 조사 → 해결**을 진행합니다.
3. `./check.sh XX` 로 통과 여부를 확인합니다.
4. 막히면 `SOLUTION.md` 를 참고합니다 (먼저 풀어보세요).

## 디렉터리 구조

```
linux-lab/
├── setup.sh              # 전체 시나리오 초기화
├── check.sh              # 자동 채점
├── scenarios/
│   ├── 01-log-incident/
│   ├── 02-permissions/
│   ├── 03-disk-full/
│   ├── 04-process-incident/
│   ├── 05-cron-failure/
│   └── 06-service-down/
└── shared/               # 공통 샘플 데이터
```

## 에이전트와 함께 연습하기

채팅에서 예시:

- "01번 시나리오 힌트만 줘"
- "`access.log`에서 500 에러 IP Top 3 구하는 명령 알려줘"
- "내가 실행한 결과 해석해줘: ..."

명령 실행은 에이전트에게 요청하거나 Terminal 탭에서 직접 입력하면 됩니다.
