#!/usr/bin/env bash
# systemctl の代わりに使う簡易サービス管理（Cloud 対応）
set -euo pipefail
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONF="$DIR/service.conf"
# shellcheck source=/dev/null
source "$CONF"

# 相対パスをシナリオディレクトリ基準に
[[ "$SCRIPT_PATH" != /* ]] && SCRIPT_PATH="$DIR/$SCRIPT_PATH"
[[ "$PID_FILE" != /* ]] && PID_FILE="$DIR/$PID_FILE"
[[ "$LOG_FILE" != /* ]] && LOG_FILE="$DIR/$LOG_FILE"

usage() {
  echo "使い方: $0 {start|stop|status|logs}"
  exit 1
}

[[ $# -eq 1 ]] || usage
mkdir -p "$(dirname "$PID_FILE")" "$(dirname "$LOG_FILE")"

case "$1" in
  start)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "already running (pid $(cat "$PID_FILE"))"
      exit 0
    fi
    if [[ ! -x "$SCRIPT_PATH" ]]; then
      echo "ERROR: スクリプトが見つからないか実行不可: $SCRIPT_PATH"
      exit 1
    fi
    LAB_WEB_PORT="$PORT" nohup "$SCRIPT_PATH" >>"$LOG_FILE" 2>&1 &
    pid=$!
    echo "$pid" >"$PID_FILE"
    sleep 1
    if kill -0 "$pid" 2>/dev/null; then
      echo "started pid $pid on port $PORT"
    else
      echo "ERROR: 起動直後に終了しました。logs を確認: $LOG_FILE"
      tail -5 "$LOG_FILE" 2>/dev/null || true
      rm -f "$PID_FILE"
      exit 1
    fi
    ;;
  stop)
    if [[ -f "$PID_FILE" ]]; then
      kill "$(cat "$PID_FILE")" 2>/dev/null || true
      rm -f "$PID_FILE"
      echo "stopped"
    else
      pkill -f "$DIR/bin/web.sh" 2>/dev/null || true
      echo "stopped (no pid file)"
    fi
    ;;
  status)
    if [[ -f "$PID_FILE" ]] && kill -0 "$(cat "$PID_FILE")" 2>/dev/null; then
      echo "● $SERVICE_NAME — active (running) pid $(cat "$PID_FILE") port $PORT"
      (ss -tln 2>/dev/null || netstat -tln 2>/dev/null) | grep ":$PORT " || true
    else
      echo "● $SERVICE_NAME — inactive (dead)"
      exit 3
    fi
    ;;
  logs)
    tail -n 20 "$LOG_FILE" 2>/dev/null || echo "(ログなし)"
    ;;
  *) usage ;;
esac
