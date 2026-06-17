#!/bin/bash
# DB mock — 5432 포트 리스닝 (실습용)
while true; do nc -l -p 5432 -q 1 >/dev/null 2>&1; done
