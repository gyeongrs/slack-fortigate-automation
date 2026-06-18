#!/usr/bin/env bash
# Linux 演習環境の初期化 — シナリオごとに障害状態を生成します
set -euo pipefail

LAB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$LAB_ROOT"

echo "==> Linux Lab 初期化中..."

# ── 共通データ ──────────────────────────────────────────────
mkdir -p shared/{logs,data,tmp}

cat > shared/logs/access.log << 'EOF'
2026-06-12T09:00:01Z 192.168.1.10 GET /api/users 200 45ms
2026-06-12T09:00:02Z 192.168.1.11 GET /api/users 200 52ms
2026-06-12T09:00:03Z 10.0.0.99 GET /admin 403 12ms
2026-06-12T09:00:04Z 192.168.1.10 GET /api/orders 200 88ms
2026-06-12T09:00:05Z 10.0.0.99 POST /login 401 8ms
2026-06-12T09:00:06Z 10.0.0.99 POST /login 401 7ms
2026-06-12T09:00:07Z 10.0.0.99 POST /login 401 9ms
2026-06-12T09:00:08Z 10.0.0.99 GET /api/users 500 1200ms
2026-06-12T09:00:09Z 10.0.0.99 GET /api/users 500 980ms
2026-06-12T09:00:10Z 10.0.0.99 GET /api/users 500 1100ms
2026-06-12T09:00:11Z 192.168.1.12 GET /health 200 3ms
2026-06-12T09:00:12Z 10.0.0.99 GET /api/orders 500 950ms
2026-06-12T09:00:13Z 10.0.0.99 GET /api/orders 500 1020ms
2026-06-12T09:00:14Z 192.168.1.10 GET /api/users 200 41ms
2026-06-12T09:00:15Z 10.0.0.99 DELETE /api/item/1 500 800ms
2026-06-12T09:00:16Z 10.0.0.5 GET /api/users 200 38ms
2026-06-12T09:00:17Z 10.0.0.99 GET /api/users 500 1150ms
2026-06-12T09:00:18Z 10.0.0.99 GET /api/users 500 990ms
2026-06-12T09:00:19Z 10.0.0.99 GET /api/users 500 1050ms
2026-06-12T09:00:20Z 192.168.1.11 GET /health 200 2ms
EOF

cat > shared/logs/app.log << 'EOF'
2026-06-12T09:00:08 ERROR db connection timeout host=db.internal
2026-06-12T09:00:09 ERROR db connection timeout host=db.internal
2026-06-12T09:00:10 WARN  retry attempt 1 for user sync
2026-06-12T09:00:12 ERROR db connection timeout host=db.internal
2026-06-12T09:00:15 ERROR out of memory during batch job
2026-06-12T09:00:17 ERROR db connection timeout host=db.internal
EOF

cat > shared/data/users.csv << 'EOF'
id,name,team,status
1,alice,engineering,active
2,bob,sales,active
3,charlie,engineering,inactive
4,diana,hr,active
EOF

# ── 01 ログ分析 ─────────────────────────────────────────────
S01="$LAB_ROOT/scenarios/01-log-incident"
mkdir -p "$S01/data"
cp shared/logs/access.log "$S01/data/access.log"
cp shared/logs/app.log "$S01/data/app.log"
cat > "$S01/data/incident.txt" << 'EOF'
[障害チケット INC-2026-0612]
症状: 09:00頃 API 応答遅延および 500 エラー急増
影響: /api/users, /api/orders エンドポイント
担当: オンコールエンジニア（あなた）
EOF

# ── 02 権限問題 ─────────────────────────────────────────────
S02="$LAB_ROOT/scenarios/02-permissions"
mkdir -p "$S02/app/"{bin,config,data}
cat > "$S02/app/bin/deploy.sh" << 'EOF'
#!/bin/bash
echo "Deploy OK: $(date -Iseconds)"
EOF
cat > "$S02/app/config/db.env" << 'EOF'
DB_HOST=db.internal
DB_USER=appuser
DB_PASS=SuperSecret123!
EOF
echo "production data" > "$S02/app/data/records.db"
chmod 644 "$S02/app/bin/deploy.sh"      # 実行権限なし（障害）
chmod 644 "$S02/app/config/db.env"      # world-readable（セキュリティ問題）
chmod 777 "$S02/app/data"               # 過剰な権限

# ── 03 ディスク不足 ───────────────────────────────────────────
S03="$LAB_ROOT/scenarios/03-disk-full"
mkdir -p "$S03/var/log/"{nginx,app,archive}
# 大きなダミーログ（約 5MB x 3 = 15MB — 演習用）
for name in nginx/access.log.1 app/app.log.1 app/app.log.2; do
  dd if=/dev/zero bs=1M count=5 of="$S03/var/log/$name" status=none 2>/dev/null
done
# 古いアーカイブ
for i in 1 2 3 4 5; do
  echo "old log chunk $i" > "$S03/var/log/archive/backup-2026-0$i.log"
done
cat > "$S03/var/log/disk-alert.txt" << 'EOF'
ALERT: /var/log usage above 85% threshold
Action required: identify large files and clean up old logs
EOF

# ── 04 プロセス障害 ─────────────────────────────────────────
S04="$LAB_ROOT/scenarios/04-process-incident"
mkdir -p "$S04/bin"
cat > "$S04/bin/runaway.sh" << 'EOF'
#!/bin/bash
# CPU 消費プロセス（演習用）
while true; do :; done
EOF
chmod +x "$S04/bin/runaway.sh"
# 既存 runaway プロセスを整理して再起動
pkill -f "scenarios/04-process-incident/bin/runaway.sh" 2>/dev/null || true
nohup "$S04/bin/runaway.sh" > /dev/null 2>&1 &
echo $! > "$S04/runaway.pid"
cat > "$S04/incident.txt" << EOF
[障害チケット INC-2026-0612-CPU]
症状: Web サーバー CPU 100% — 応答遅延
ヒント: runaway プロセス PID ファイル → $S04/runaway.pid
EOF

# ── 05 cron バックアップ失敗 ────────────────────────────────────
S05="$LAB_ROOT/scenarios/05-cron-failure"
mkdir -p "$S05/"{scripts,logs,backup}
cat > "$S05/scripts/backup.sh" << 'EOF'
#!/bin/bash
SRC="/workspace/linux-lab/scenarios/05-cron-failure/data"
DST="/workspace/linux-lab/scenarios/05-cron-failure/backup"
LOG="/workspace/linux-lab/scenarios/05-cron-failure/logs/backup.log"
mkdir -p "$DST"
if [[ ! -d "$SRC" ]]; then
  echo "$(date -Iseconds) ERROR source missing: $SRC" >> "$LOG"
  exit 1
fi
cp -r "$SRC"/* "$DST"/
echo "$(date -Iseconds) OK backup completed" >> "$LOG"
EOF
chmod +x "$S05/scripts/backup.sh"
mkdir -p "$S05/data"
echo "important record 1" > "$S05/data/records.txt"
echo "important record 2" >> "$S05/data/records.txt"
# 誤った cron エントリ（パスの typo）
cat > "$S05/crontab.broken" << 'EOF'
# 毎日 02:00 バックアップ — パス typo で失敗中
0 2 * * * /workspace/linux-lab/scenarios/05-cron-failure/scripts/backp.sh
EOF
echo "$(date -Iseconds) ERROR: backp.sh not found" > "$S05/logs/backup.log"

# ── 06 サービス接続失敗 ──────────────────────────────────────
S06="$LAB_ROOT/scenarios/06-service-down"
mkdir -p "$S06/config"
cat > "$S06/config/app.env" << 'EOF'
APP_PORT=8080
DB_HOST=db.internal
DB_PORT=5432
EOF
cat > "$S06/config/hosts.snippet" << 'EOF'
# /etc/hosts に追加すべき項目（未登録）
127.0.0.1 db.internal
EOF
cat > "$S06/mock-server.sh" << 'EOF'
#!/bin/bash
# DB mock — 5432 ポートでリッスン（演習用）
while true; do nc -l -p 5432 -q 1 >/dev/null 2>&1; done
EOF
chmod +x "$S06/mock-server.sh"
pkill -f "scenarios/06-service-down/mock-server.sh" 2>/dev/null || true
# 意図的に mock サーバーを起動しない → 接続失敗状態
cat > "$S06/incident.txt" << 'EOF'
[障害チケット INC-2026-0612-DB]
症状: app → db.internal:5432 接続拒否 (Connection refused)
確認: config/app.env, hosts, ポートリッスン状態
EOF

# ── 07 サービス復旧（Cloud 対応 — systemctl 不要）────────────
S07="$LAB_ROOT/scenarios/07-service-recovery"
mkdir -p "$S07"/{bin,run,logs}
chmod +x "$S07/bin/web.sh" "$S07/svc-manage.sh" 2>/dev/null || true
WEB_SCRIPT="$S07/bin/web.sh"
cat > "$S07/service.conf" << EOF
# lab-web サービス設定（Cloud 演習用）
SERVICE_NAME=lab-web
SCRIPT_PATH=/wrong/path/web.sh
PORT=8088
PID_FILE=run/lab-web.pid
LOG_FILE=logs/web.log
EOF
pkill -f "07-service-recovery/bin/web.sh" 2>/dev/null || true
pkill -f "HTTPServer.*8088" 2>/dev/null || true
if command -v lsof >/dev/null 2>&1; then
  lsof -t -i:8088 2>/dev/null | xargs -r kill 2>/dev/null || true
fi
rm -f "$S07/run/lab-web.pid" "$S07/logs/web.log"
cat > "$S07/incident.txt" << EOF
[障害チケット INC-2026-0612-WEB]
症状: lab-web がポート 8088 で応答しない
確認: ./svc-manage.sh status / service.conf の SCRIPT_PATH
正しいパス: $WEB_SCRIPT
EOF

echo "==> 初期化完了。./check.sh で状態を確認"
echo "    全シナリオ Cloud Terminal で実施可能（01〜07）"
