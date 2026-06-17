# 시나리오 03 — 해설

```bash
cd /workspace/linux-lab/scenarios/03-disk-full

# 현황 파악
du -sh var/log/*
find var/log -type f -size +1M

# 방법 A: 압축
find var/log -type f -size +1M -exec gzip -v {} \;

# 방법 B: 삭제
find var/log -type f -size +1M -delete

# 오래된 아카이브 정리
rm -f var/log/archive/backup-2026-0{1,2,3}.log

# 확인
find var/log -type f -size +1M | wc -l   # → 0
```

## 실무 팁

```bash
# logrotate 예시 (/etc/logrotate.d/app)
/var/log/app/*.log {
    daily
    rotate 7
    compress
    missingok
}
```
