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
