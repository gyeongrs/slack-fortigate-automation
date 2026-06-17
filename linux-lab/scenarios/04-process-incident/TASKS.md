# 시나리오 04: CPU 100% — runaway 프로세스

## 실무 배경

웹 서버 **CPU 100%** 알람. 배치/루프 프로세스가 응답을 막고 있습니다.

## 증상

- 시스템 느림
- `incident.txt` 참고
- `bin/runaway.sh` — CPU 소모 무한 루프 (의도적)

## 미션

1. CPU 사용 상위 프로세스 확인 (`ps`, `top`)
2. `runaway.sh` **PID** 찾기
3. 프로세스 **종료** (`kill`)
4. 종료 확인 (`pgrep` 또는 `ps`)

## 힌트

```bash
cd /workspace/linux-lab/scenarios/04-process-incident

# CPU 순 정렬
ps aux --sort=-%cpu | head -10

# runaway 찾기
pgrep -af runaway

# PID 파일 참고
cat runaway.pid

# 종료
kill $(cat runaway.pid)
# 또는
pkill -f runaway.sh
```

## 완료 확인

```bash
cd /workspace/linux-lab
./check.sh 04
```

## 실무 연결

- `kill -15` (SIGTERM) → 대기 → `kill -9` (SIGKILL)
- systemd: `systemctl stop`, `Restart=on-failure`
- CPU limit: cgroups, ulimit

## 정답

[SOLUTION.md](SOLUTION.md)
