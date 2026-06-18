# シナリオ 03 — 解説

```bash
cd /workspace/linux-lab/scenarios/03-disk-full

# 現状把握
du -sh var/log/*
find var/log -type f -size +1M

# 方法 A: 圧縮
find var/log -type f -size +1M -exec gzip -v {} \;

# 方法 B: 削除
find var/log -type f -size +1M -delete

# 古いアーカイブ整理
rm -f var/log/archive/backup-2026-0{1,2,3}.log

# 確認
find var/log -type f -size +1M | wc -l   # → 0
```

## 実務のヒント

```bash
# logrotate 例 (/etc/logrotate.d/app)
/var/log/app/*.log {
    daily
    rotate 7
    compress
    missingok
}
```
