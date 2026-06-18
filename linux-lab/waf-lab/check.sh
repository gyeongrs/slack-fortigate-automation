#!/usr/bin/env bash
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"
PASS=0 FAIL=0
ok() { echo "  [PASS] $1"; PASS=$((PASS+1)); }
ng() { echo "  [FAIL] $1"; FAIL=$((FAIL+1)); }

echo "WAF Lab 採点"
echo "============"

if ! sudo docker info >/dev/null 2>&1; then
  ng "Docker 未起動 — ./start.sh を実行"
  exit 1
fi

if sudo docker compose ps --status running 2>/dev/null | grep -q waf-lab; then
  ok "コンテナ実行中"
else
  ng "コンテナ未実行 — ./start.sh"
fi

# 正常リクエスト
code=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/ 2>/dev/null || echo 000)
if [[ "$code" =~ ^(200|301|302)$ ]]; then
  ok "正常 GET / → HTTP $code"
else
  ng "正常 GET / → HTTP $code（期待 200/301/302）"
fi

# SQLi 風ペイロード（ブロック期待）
sqli_code=$(curl -s -o /dev/null -w "%{http_code}" -G \
  "http://127.0.0.1:8080/rest/products/search" \
  --data-urlencode "q=' OR 1=1--" 2>/dev/null || echo 000)
if [[ "$sqli_code" == "403" ]]; then
  ok "SQLi 風リクエスト → 403 ブロック"
elif [[ "$sqli_code" == "200" ]]; then
  ng "SQLi 風リクエスト → 200（WAF がブロックしていない）"
else
  ng "SQLi 風リクエスト → HTTP $sqli_code（期待 403）"
fi

echo "============"
echo "PASS: $PASS  FAIL: $FAIL"
[[ "$FAIL" -eq 0 ]]
