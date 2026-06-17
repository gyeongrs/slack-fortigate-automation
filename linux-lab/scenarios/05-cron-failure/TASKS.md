# 시나리오 05: cron 백업 실패

## 실무 배경

매일 02:00 **백업 job**이 실패. `backup/` 디렉터리가 비어 있습니다.

## 증상

- `logs/backup.log`: `ERROR: backp.sh not found`
- `crontab.broken`에 **오타** 있는 cron 항목
- `data/records.txt`는 존재하나 backup/ 에 복사 안 됨

## 미션

1. `logs/backup.log`에서 **실패 원인** 확인
2. `crontab.broken`의 **경로 오타** 수정 (`backp.sh` → `backup.sh`)
3. `scripts/backup.sh` **수동 실행**
4. `backup/records.txt` 생성 및 log에 `OK backup completed` 확인

## 힌트

```bash
cd /workspace/linux-lab/scenarios/05-cron-failure

cat logs/backup.log
cat crontab.broken
cat scripts/backup.sh

# 오타 수정 (편집기)
nano crontab.broken

# 수동 백업
bash scripts/backup.sh
cat logs/backup.log
ls -la backup/
```

## 완료 확인

```bash
cd /workspace/linux-lab
./check.sh 05
```

## 실무 연결

- cron 로그: `/var/log/syslog` 또는 `journalctl -u cron`
- `MAILTO=` 설정으로 실패 알림
- 절대경로 사용, 스크립트 `chmod +x`

## 정답

[SOLUTION.md](SOLUTION.md)
