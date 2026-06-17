# 시나리오 05 — 해설

```bash
cd /workspace/linux-lab/scenarios/05-cron-failure

# 원인: backp.sh 오타
sed -i 's/backp\.sh/backup.sh/' crontab.broken
cat crontab.broken

# 백업 실행
bash scripts/backup.sh
cat logs/backup.log
ls backup/
```

## crontab.broken 수정 후

```
0 2 * * * /workspace/linux-lab/scenarios/05-cron-failure/scripts/backup.sh
```

## 실무 cron 체크리스트

- [ ] 절대 경로
- [ ] 실행 권한
- [ ] 로그 리다이렉션 `>> /var/log/backup.log 2>&1`
- [ ] 실패 시 알림
