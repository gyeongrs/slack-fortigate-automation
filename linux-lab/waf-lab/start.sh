#!/usr/bin/env bash
# WAF ラボ起動（Docker + ModSecurity + Juice Shop）
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

echo "==> WAF Lab 起動"

# Docker デーモン確認
if ! sudo docker info >/dev/null 2>&1; then
  echo "Docker 未起動 → start-docker.sh を実行"
  bash "$DIR/../start-docker.sh"
fi

echo "==> イメージ取得 & コンテナ起動（初回は数分かかります）"
sudo docker compose pull
sudo docker compose up -d

echo "==> 起動待ち（Juice Shop + WAF、最大 90 秒）..."
for i in $(seq 1 30); do
  js=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000/ 2>/dev/null || echo 000)
  waf=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/ 2>/dev/null || echo 000)
  if [[ "$js" =~ ^(200|301|302)$ ]] && [[ "$waf" =~ ^(200|301|302)$ ]]; then
    echo "==> 起動完了"
    echo ""
    echo "  Juice Shop (WAF 経由): http://127.0.0.1:8080"
    echo "  直接（比較用・内部）:    juice-shop:3000（コンテナ内のみ）"
    echo ""
    echo "  演習: cat scenarios/01-sqli-test.md"
    echo "  採点: ./check.sh"
    exit 0
  fi
  sleep 3
done

echo "Juice Shop: HTTP ${js:-?}  WAF: HTTP ${waf:-?}"

echo "起動タイムアウト。ログ確認:"
sudo docker compose logs --tail=30
exit 1
