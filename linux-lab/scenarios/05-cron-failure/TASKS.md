# シナリオ 05: cron バックアップ失敗

## 実務背景

毎日 02:00 の **バックアップ job** が失敗。`backup/` ディレクトリが空です。

## 症状

- `logs/backup.log`: `ERROR: backp.sh not found`
- `crontab.broken` に **typo** がある cron エントリ
- `data/records.txt` は存在するが backup/ にコピーされていない

## ミッション

1. `logs/backup.log` で **失敗原因** を確認
2. `crontab.broken` の **パス typo** を修正（`backp.sh` → `backup.sh`）
3. `scripts/backup.sh` を **手動実行**
4. `backup/records.txt` 作成と log に `OK backup completed` があることを確認

## ヒント

```bash
cd /workspace/linux-lab/scenarios/05-cron-failure

cat logs/backup.log
cat crontab.broken
cat scripts/backup.sh

# typo 修正（エディタ）
nano crontab.broken

# 手動バックアップ
bash scripts/backup.sh
cat logs/backup.log
ls -la backup/
```

## 完了確認

```bash
cd /workspace/linux-lab
./check.sh 05
```

## 実務との関連

- cron ログ: `/var/log/syslog` または `journalctl -u cron`
- `MAILTO=` 設定で失敗通知
- 絶対パス使用、スクリプト `chmod +x`

## 解答

[SOLUTION.md](SOLUTION.md)
