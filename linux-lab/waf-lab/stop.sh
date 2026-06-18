#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
sudo docker compose down 2>/dev/null || true
echo "WAF Lab 停止完了"
