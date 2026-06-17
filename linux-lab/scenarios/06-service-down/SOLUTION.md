# シナリオ 06 — 解説

## 方法 A: Python mock（推奨 — nc 不要）

```bash
cd /workspace/linux-lab/scenarios/06-service-down

python3 << 'PY' &
import socket, time
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 5432))
s.listen(5)
print("mock db listening on 5432", flush=True)
while True:
    c, addr = s.accept()
    c.close()
PY

sleep 1
ss -tln | grep 5432
```

## 方法 B: mock-server.sh（nc 必要）

```bash
sudo apt install -y netcat-openbsd   # 必要な場合
nohup ./mock-server.sh > /tmp/mock-db.log 2>&1 &
ss -tln | grep 5432
```

## hosts（任意）

```bash
# db.internal 名前解決（sudo が必要な場合あり）
echo "127.0.0.1 db.internal" | sudo tee -a /etc/hosts
getent hosts db.internal
```

## トラブルシューティング順序（実務）

1. アプリ設定（host/port）
2. DNS/hosts
3. ポートリッスン（`ss -tlnp`）
4. ローカル接続（`nc -zv host port`）
5. ファイアウォール/ACL
6. DB サービスログ
