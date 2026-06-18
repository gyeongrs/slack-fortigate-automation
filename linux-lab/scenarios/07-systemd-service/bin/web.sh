#!/bin/bash
# 演習用 — 常駐してログに heartbeat を出す
while true; do
  echo "$(date -Iseconds) lab-web heartbeat"
  sleep 30
done
