# シナリオ 05 — 解説

```bash
cd /workspace/linux-lab/scenarios/05-cron-failure

# 原因: backp.sh の typo
sed -i 's/backp\.sh/backup.sh/' crontab.broken
cat crontab.broken

# バックアップ実行
bash scripts/backup.sh
cat logs/backup.log
ls backup/
```

## crontab.broken 修正後

```
0 2 * * * /workspace/linux-lab/scenarios/05-cron-failure/scripts/backup.sh
```

## 実務 cron チェックリスト

- [ ] 絶対パス
- [ ] 実行権限
- [ ] ログリダイレクト `>> /var/log/backup.log 2>&1`
- [ ] 失敗時の通知
