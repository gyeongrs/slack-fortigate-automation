# 시나리오 03: 디스크 부족 (로그로 /var/log Full)

## 실무 배경

디스크 사용률 **85% 초과** 알람. `/var/log` 아래 대용량 로그가 원인입니다.

## 증상

- `var/log/disk-alert.txt` 알람 파일 존재
- `var/log/` 아래 **5MB짜리 로그** 다수
- 오래된 `archive/` 백업 로그 누적

## 미션

1. `var/log/`에서 **1MB 이상 파일** 목록 확인 (`find` 또는 `du`)
2. 대용량 `.log.1`, `.log.2` 파일을 **삭제하거나 gzip 압축**
3. `archive/` 내 **30일 이상 된 로그** 정리 (실습용: `backup-2026-01~03.log` 삭제)
4. 정리 후 1MB 초과 파일 **0개** 확인

## 힌트

```bash
cd /workspace/linux-lab/scenarios/03-disk-full

du -sh var/log/*
du -ah var/log/ | sort -rh | head -10

find var/log -type f -size +1M -ls
find var/log -type f -size +1M -exec gzip {} \;
# 또는
find var/log -type f -size +1M -delete
```

## 완료 확인

```bash
cd /workspace/linux-lab
./check.sh 03
```

## 실무 연결

- logrotate 설정 점검
- `/var/log` 별도 파티션
- 알람: 80% warn, 90% critical

## 정답

[SOLUTION.md](SOLUTION.md)
