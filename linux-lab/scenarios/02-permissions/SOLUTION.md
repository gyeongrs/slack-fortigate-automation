# 시나리오 02 — 해설

```bash
cd /workspace/linux-lab/scenarios/02-permissions

chmod +x app/bin/deploy.sh
chmod 600 app/config/db.env
chmod 750 app/data

./app/bin/deploy.sh
```

## 권한 표

| 파일 | Before | After | 이유 |
|------|--------|-------|------|
| deploy.sh | 644 | 755 (+x) | 실행 필요 |
| db.env | 644 | 600 | 비밀번호 보호 |
| data/ | 777 | 750 | others 쓰기 차단 |

## 확인

```bash
ls -la app/bin/ app/config/ app/data/
./check.sh 02
```
