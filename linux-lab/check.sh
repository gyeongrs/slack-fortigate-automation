#!/usr/bin/env bash
# 시나리오별 자동 점검
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
  if [[ ! -f "$log" ]]; then ng "access.log 없음 — ./setup.sh 실행"; return; fi

  local err_ip count_500 top_path
  # log format: TIMESTAMP IP METHOD PATH STATUS LATENCY
  err_ip=$(awk '$5 == 500 {print $2}' "$log" | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')
  count_500=$(awk '$5 == 500' "$log" | wc -l)
  top_path=$(awk '$5 == 500 {print $4}' "$log" | sort | uniq -c | sort -rn | head -1 | awk '{print $2}')

  [[ "$err_ip" == "10.0.0.99" ]] && ok "500 에러 주범 IP = 10.0.0.99" || ng "500 에러 IP 분석 (정답: 10.0.0.99, 현재: ${err_ip:-none})"
  [[ "$count_500" -ge 9 ]] && ok "500 에러 ${count_500}건 확인" || ng "500 에러 카운트 (기대 ≥9, 현재: $count_500)"
  [[ "$top_path" == "/api/users" ]] && ok "최다 500 경로 = /api/users" || ng "500 최다 경로 (정답: /api/users, 현재: ${top_path:-none})"

  if [[ -f "$LAB_ROOT/scenarios/01-log-incident/answer.txt" ]]; then
    ok "answer.txt 작성됨"
  else
    info "answer.txt 미작성 — TASKS.md 참고 (선택)"
  fi
}

check_02() {
  echo "==> 02-permissions"
  local deploy="$LAB_ROOT/scenarios/02-permissions/app/bin/deploy.sh"
  local dbenv="$LAB_ROOT/scenarios/02-permissions/app/config/db.env"
  local datadir="$LAB_ROOT/scenarios/02-permissions/app/data"

  [[ -x "$deploy" ]] && ok "deploy.sh 실행 가능" || ng "deploy.sh +x 필요 (chmod +x)"
  [[ "$(stat -c '%a' "$dbenv" 2>/dev/null)" == "600" ]] && ok "db.env 권한 600" || ng "db.env → chmod 600 (현재: $(stat -c '%a' "$dbenv" 2>/dev/null || echo ?))"
  [[ "$(stat -c '%a' "$datadir" 2>/dev/null)" == "750" ]] && ok "data/ 권한 750" || ng "data/ → chmod 750 (현재: $(stat -c '%a' "$datadir" 2>/dev/null || echo ?))"

  if [[ -x "$deploy" ]] && "$deploy" >/dev/null 2>&1; then
    ok "deploy.sh 실행 성공"
  else
    ng "deploy.sh 실행 실패"
  fi
}

check_03() {
  echo "==> 03-disk-full"
  local logdir="$LAB_ROOT/scenarios/03-disk-full/var/log"
  local big_count compressed

  big_count=$(find "$logdir" -type f -size +1M 2>/dev/null | wc -l)
  compressed=$(find "$logdir" -name "*.gz" 2>/dev/null | wc -l)

  if [[ "$big_count" -eq 0 ]]; then
    ok "1MB 초과 파일 정리 완료"
  else
    ng "대용량 파일 ${big_count}개 남음 — du/find 로 확인 후 삭제 또는 gzip"
  fi

  if [[ "$compressed" -gt 0 ]] || [[ "$big_count" -eq 0 ]]; then
    ok "디스크 정리 조치 확인"
  fi
}

check_04() {
  echo "==> 04-process-incident"
  local running
  running=$(pgrep -f "scenarios/04-process-incident/bin/runaway.sh" 2>/dev/null | wc -l || echo 0)
  if [[ "$running" -eq 0 ]]; then
    ok "runaway 프로세스 종료됨"
  else
    ng "runaway 프로세스 ${running}개 실행 중 — ps/pkill 로 종료"
  fi
}

check_05() {
  echo "==> 05-cron-failure"
  local script="$LAB_ROOT/scenarios/05-cron-failure/scripts/backup.sh"
  local backup_dir="$LAB_ROOT/scenarios/05-cron-failure/backup"
  local log="$LAB_ROOT/scenarios/05-cron-failure/logs/backup.log"
  local cron="$LAB_ROOT/scenarios/05-cron-failure/crontab.broken"

  if grep -q 'backp\.sh' "$cron" 2>/dev/null; then
    ng "crontab.broken 경로 오타 미수정 (backp.sh → backup.sh)"
  else
    ok "crontab.broken 경로 수정됨"
  fi

  if [[ -f "$backup_dir/records.txt" ]]; then
    ok "백업 파일 존재"
  else
    info "백업 미실행 — $script 수동 실행 후 재점검"
    if bash "$script" 2>/dev/null && [[ -f "$backup_dir/records.txt" ]]; then
      ok "backup.sh 수동 실행 성공"
    else
      ng "backup.sh 실행 필요"
    fi
  fi

  if grep -q "OK backup completed" "$log" 2>/dev/null; then
    ok "backup.log 성공 기록"
  else
    ng "backup.log 에 OK 기록 없음"
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
    ok "5432 포트 리스닝 중"
  else
    ng "5432 미리스닝 — mock-server.sh 백그라운드 실행 필요"
  fi

  if getent hosts db.internal >/dev/null 2>&1 || grep -q 'db.internal' /etc/hosts 2>/dev/null; then
    ok "db.internal 호스트 해석 가능"
  else
    info "db.internal 미등록 — /etc/hosts 추가 또는 nc 127.0.0.1 5432 로 테스트"
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
    *) echo "Unknown scenario: $1"; exit 1 ;;
  esac
}

echo "Linux Lab 점검"
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
