# シナリオ 06: DB 接続失敗 (Connection refused)

## 実務背景

アプリ起動後 **db.internal:5432 Connection refused**。
デプロイ直後の DB 接続設定問題でサービス down。

## 症状

- `config/app.env`: `DB_HOST=db.internal`, `DB_PORT=5432`
- 5432 ポート **未リッスン**
- `hosts.snippet` — `/etc/hosts` 登録が必要（任意）

## ミッション

1. `config/app.env` 設定を確認
2. **5432 ポート** のリッスン状態を確認（`ss -tln` または `netstat`）
3. `mock-server.sh` を **バックグラウンド** で実行し DB mock を起動
4. `nc -zv 127.0.0.1 5432` または `ss -tln | grep 5432` で接続確認

## ヒント

```bash
cd /workspace/linux-lab/scenarios/06-service-down

cat config/app.env
cat incident.txt

ss -tln | grep 5432

# mock DB サーバー起動（openbsd-netcat が必要な場合あり）
nohup ./mock-server.sh > /tmp/mock-db.log 2>&1 &

# または Python で簡易 mock
python3 -c "
import socket
s=socket.socket()
s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(('127.0.0.1',5432))
s.listen(1)
print('listening 5432')
import time
time.sleep(3600)
" &

ss -tln | grep 5432
```

## 完了確認

```bash
cd /workspace/linux-lab
./check.sh 06
```

## 実務との関連

- `telnet/nc` ポート probe
- DNS: `getent hosts db.internal`
- ファイアウォール: `iptables -L`, security group
- アプリログ + DB ログの相関分析

## 解答

[SOLUTION.md](SOLUTION.md)
