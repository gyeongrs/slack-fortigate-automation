#!/bin/bash
# DB mock — 5432 ポートでリッスン（演習用）
while true; do nc -l -p 5432 -q 1 >/dev/null 2>&1; done
