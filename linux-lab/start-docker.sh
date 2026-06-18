#!/usr/bin/env bash
# Cursor Cloud VM 用 Docker 起動スクリプト
# systemd がないため dockerd を手動起動（storage-driver=vfs）
set -euo pipefail

if docker info >/dev/null 2>&1; then
  echo "Docker は既に動作中です"
  docker --version
  docker ps
  exit 0
fi

if ! command -v dockerd >/dev/null 2>&1; then
  echo "Docker 未インストール。インストール中..."
  sudo apt-get update -qq
sudo apt-get install -y docker.io docker-compose-v2 2>/dev/null || true
fi

echo "dockerd 起動中（vfs ストレージ）..."
sudo pkill dockerd 2>/dev/null || true
sleep 1
sudo dockerd --storage-driver=vfs > /tmp/dockerd.log 2>&1 &
for i in $(seq 1 30); do
  if sudo docker info >/dev/null 2>&1; then
    echo "Docker 起動完了"
    docker --version
    echo ""
    echo "テスト: sudo docker run --rm hello-world"
    exit 0
  fi
  sleep 1
done
echo "起動失敗。ログ: /tmp/dockerd.log"
tail -20 /tmp/dockerd.log
exit 1
