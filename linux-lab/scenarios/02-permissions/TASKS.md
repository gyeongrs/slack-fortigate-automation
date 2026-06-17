# シナリオ 02: 権限問題（デプロイスクリプト実行不可）

## 実務背景

デプロイ担当者が **deploy.sh 実行失敗** および **セキュリティ監査で db.env 漏洩** の指摘を受けました。

## 症状

```bash
./app/bin/deploy.sh
# bash: ./app/bin/deploy.sh: Permission denied
```

- `app/config/db.env` — DB パスワード含む、権限過多
- `app/data/` — world-writable (777)

## ミッション

1. `deploy.sh` が **実行できるよう** 権限を修正
2. `db.env` を **所有者のみ読み取り (600)** に変更
3. `app/data/` を **750** に変更（グループ読み/実行、others 拒否）
4. `./app/bin/deploy.sh` 実行後 "Deploy OK" 出力を確認

## ヒント

```bash
cd /workspace/linux-lab/scenarios/02-permissions

ls -la app/bin/deploy.sh
ls -la app/config/db.env
ls -lad app/data/

stat -c '%a %n' app/bin/deploy.sh app/config/db.env app/data/
```

## 完了確認

```bash
cd /workspace/linux-lab
./check.sh 02
```

## 実務との関連

- `.env`, API キー: 600 または 640、root 所有
- 実行スクリプト: 750
- データディレクトリ: 750/770、others 禁止

## 解答

[SOLUTION.md](SOLUTION.md)
