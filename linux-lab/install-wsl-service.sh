#!/usr/bin/env bash
# WSL 用 — 壊れた lab-web.service をユーザーサービスとして登録
set -euo pipefail

LAB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
S07="$LAB_ROOT/scenarios/07-systemd-service"

if ! command -v systemctl >/dev/null 2>&1; then
  echo "[ERROR] systemctl がありません。WSL-SETUP.md を参照してください。"
  exit 1
fi

if ! systemctl --user status >/dev/null 2>&1; then
  echo "[ERROR] systemd が動いていません。"
  echo "  → sudo cp $LAB_ROOT/wsl.conf.example /etc/wsl.conf"
  echo "  → PowerShell: wsl --shutdown && wsl"
  exit 1
fi

chmod +x "$S07/bin/web.sh"

# 意図的に間違ったパスでユニット生成
cat > "$S07/lab-web.service" << EOF
[Unit]
Description=Lab Web Service for training
After=network.target

[Service]
Type=simple
ExecStart=/wrong/path/web.sh
Restart=on-failure

[Install]
WantedBy=default.target
EOF

mkdir -p ~/.config/systemd/user
cp "$S07/lab-web.service" ~/.config/systemd/user/

systemctl --user daemon-reload 2>/dev/null || true
systemctl --user stop lab-web 2>/dev/null || true
systemctl --user reset-failed lab-web 2>/dev/null || true

# 一度起動して failed 状態を作る
systemctl --user start lab-web 2>/dev/null || true

cat > "$S07/incident.txt" << EOF
[障害チケット INC-2026-0612-SVC]
症状: lab-web.service が failed
確認: systemctl --user status lab-web
ヒント: ExecStart のパスを $(realpath "$S07/bin/web.sh") に修正
EOF

echo "==> lab-web.service を壊した状態で登録しました"
echo "    cat scenarios/07-systemd-service/TASKS.md"
echo "    systemctl --user status lab-web"
