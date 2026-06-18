# シナリオ 07 — 解説

```bash
cd scenarios/07-service-recovery

chmod +x bin/web.sh svc-manage.sh

# 正しいパスを取得
WEB="$(realpath bin/web.sh)"
echo "SCRIPT_PATH=$WEB"

# service.conf を修正（例）
sed -i "s|^SCRIPT_PATH=.*|SCRIPT_PATH=$WEB|" service.conf
cat service.conf

./svc-manage.sh start
./svc-manage.sh status
curl -s http://127.0.0.1:8088/
./svc-manage.sh logs
```

## トラブル時

```bash
# ポート占有確認
ss -tln | grep 8088

# 強制停止
./svc-manage.sh stop
pkill -f "07-service-recovery/bin/web.sh" 2>/dev/null || true
```

## 片付け

```bash
./svc-manage.sh stop
```
