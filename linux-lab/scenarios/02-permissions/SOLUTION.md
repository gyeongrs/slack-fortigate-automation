# シナリオ 02 — 解説

```bash
cd /workspace/linux-lab/scenarios/02-permissions

chmod +x app/bin/deploy.sh
chmod 600 app/config/db.env
chmod 750 app/data

./app/bin/deploy.sh
```

## 権限表

| ファイル | Before | After | 理由 |
|---------|--------|-------|------|
| deploy.sh | 644 | 755 (+x) | 実行が必要 |
| db.env | 644 | 600 | パスワード保護 |
| data/ | 777 | 750 | others 書き込み拒否 |

## 確認

```bash
ls -la app/bin/ app/config/ app/data/
./check.sh 02
```
