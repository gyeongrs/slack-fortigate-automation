#!/usr/bin/env bash
# シナリオ別自動採点
set -euo pipefail

LAB_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PASS=0
FAIL=0

ok()   { echo "  [PASS] $1"; PASS=$((PASS + 1)); }
ng()   { echo "  [FAIL] $1"; FAIL=$((FAIL + 1)); }
info() { echo "  [INFO] $1"; }

check_01() {
  echo "==> 01-log-incident"
  local log="$LAB_ROOT/scenarios/01-log-incident/data/access.log"
  if [[ ! -f "$log" ]]; then ng "access.log がありません — ./setup.sh を実行"; return; fi

  local err_ip count_500 top_path
  # log format: TIMESTAMP IP METHOD PATH STATUS LATENCY
  err_ip=$(awk '$5 == 500 {print $2}' "$log" | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')
  count_500=$(awk '$5 == 500' "$log" | wc -l)
  top_path=$(awk '$5 == 500 {print $4}' "$log" | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')

  [[ "$err_ip" == "10.0.0.99" ]] && ok "500 エラー主犯 IP = 10.0.0.99" || ng "500 エラー IP 分析 (正解: 10.0.0.99, 現在: ${err_ip:-none})"
  [[ "$count_500" -ge 9 ]] && ok "500 エラー ${count_500} 件確認" || ng "500 エラーカウント (期待 ≥9, 現在: $count_500)"
  [[ "$top_path" == "/api/users" ]] && ok "最多 500 パス = /api/users" || ng "500 最多パス (正解: /api/users, 現在: ${top_path:-none})"

  if [[ -f "$LAB_ROOT/scenarios/01-log-incident/answer.txt" ]]; then
    ok "answer.txt 作成済み"
  else
    info "answer.txt 未作成 — TASKS.md 参照（任意）"
  fi
}

check_02() {
  echo "==> 02-permissions"
  local deploy="$LAB_ROOT/scenarios/02-permissions/app/bin/deploy.sh"
  local dbenv="$LAB_ROOT/scenarios/02-permissions/app/config/db.env"
  local datadir="$LAB_ROOT/scenarios/02-permissions/app/data"

  [[ -x "$deploy" ]] && ok "deploy.sh 実行可能" || ng "deploy.sh +x が必要 (chmod +x)"
  [[ "$(stat -c '%a' "$dbenv" 2>/dev/null)" == "600" ]] && ok "db.env 権限 600" || ng "db.env → chmod 600 (現在: $(stat -c '%a' "$dbenv" 2>/dev/null || echo ?))"
  [[ "$(stat -c '%a' "$datadir" 2>/dev/null)" == "750" ]] && ok "data/ 権限 750" || ng "data/ → chmod 750 (現在: $(stat -c '%a' "$datadir" 2>/dev/null || echo ?))"

  if [[ -x "$deploy" ]] && "$deploy" >/dev/null 2>&1; then
    ok "deploy.sh 実行成功"
  else
    ng "deploy.sh 実行失敗"
  fi
}

check_03() {
  echo "==> 03-disk-full"
  local logdir="$LAB_ROOT/scenarios/03-disk-full/var/log"
  local big_count compressed

  big_count=$(find "$logdir" -type f -size +1M 2>/dev/null | wc -l)
  compressed=$(find "$logdir" -name "*.gz" 2>/dev/null | wc -l)

  if [[ "$big_count" -eq 0 ]]; then
    ok "1MB 超ファイルの整理完了"
  else
    ng "大容量ファイル ${big_count} 件残存 — du/find で確認後、削除または gzip"
  fi

  if [[ "$compressed" -gt 0 ]] || [[ "$big_count" -eq 0 ]]; then
    ok "ディスク整理の実施を確認"
  fi
}

check_04() {
  echo "==> 04-process-incident"
  local running
  running=$(pgrep -f "scenarios/04-process-incident/bin/runaway.sh" 2>/dev/null | wc -l || echo 0)
  if [[ "$running" -eq 0 ]]; then
    ok "runaway プロセス終了済み"
  else
    ng "runaway プロセス ${running} 件実行中 — ps/pkill で終了"
  fi
}

check_05() {
  echo "==> 05-cron-failure"
  local script="$LAB_ROOT/scenarios/05-cron-failure/scripts/backup.sh"
  local backup_dir="$LAB_ROOT/scenarios/05-cron-failure/backup"
  local log="$LAB_ROOT/scenarios/05-cron-failure/logs/backup.log"
  local cron="$LAB_ROOT/scenarios/05-cron-failure/crontab.broken"

  if grep -q 'backp\.sh' "$cron" 2>/dev/null; then
    ng "crontab.broken パス typo 未修正 (backp.sh → backup.sh)"
  else
    ok "crontab.broken パス修正済み"
  fi

  if [[ -f "$backup_dir/records.txt" ]]; then
    ok "バックアップファイル存在"
  else
    info "バックアップ未実行 — $script を手動実行後、再採点"
    if bash "$script" 2>/dev/null && [[ -f "$backup_dir/records.txt" ]]; then
      ok "backup.sh 手動実行成功"
    else
      ng "backup.sh の実行が必要"
    fi
  fi

  if grep -q "OK backup completed" "$log" 2>/dev/null; then
    ok "backup.log に成功記録"
  else
    ng "backup.log に OK 記録なし"
  fi
}

check_06() {
  echo "==> 06-service-down"
  local listening=0
  if ss -tln 2>/dev/null | grep -q ':5432 '; then
    listening=1
  elif netstat -tln 2>/dev/null | grep -q ':5432 '; then
    listening=1
  fi
  if [[ "$listening" -gt 0 ]]; then
    ok "5432 ポートでリッスン中"
  else
    ng "5432 未リッスン — mock-server.sh をバックグラウンド実行が必要"
  fi

  if getent hosts db.internal >/dev/null 2>&1 || grep -q 'db.internal' /etc/hosts 2>/dev/null; then
    ok "db.internal ホスト名解決可能"
  else
    info "db.internal 未登録 — /etc/hosts 追加または nc 127.0.0.1 5432 でテスト"
  fi
}

run_one() {
  case "$1" in
    01|1) check_01 ;;
    02|2) check_02 ;;
    03|3) check_03 ;;
    04|4) check_04 ;;
    05|5) check_05 ;;
    06|6) check_06 ;;
    *) echo "不明なシナリオ: $1"; exit 1 ;;
  esac
}

echo "Linux Lab 採点"
echo "=============="

if [[ $# -eq 0 ]]; then
  check_01; echo
  check_02; echo
  check_03; echo
  check_04; echo
  check_05; echo
  check_06; echo
else
  run_one "$1"
fi

echo
echo "=============="
echo "PASS: $PASS  FAIL: $FAIL"
[[ "$FAIL" -eq 0 ]] && exit 0 || exit 1
