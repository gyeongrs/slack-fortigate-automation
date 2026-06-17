# 시나리오 01 — 해설

## 정답 요약

| 항목 | 값 |
|------|-----|
| 500 에러 건수 | 9건 |
| 주범 IP | 10.0.0.99 |
| 최다 500 경로 | /api/users |
| app.log 원인 | db connection timeout |

## 명령 예시

```bash
cd /workspace/linux-lab/scenarios/01-log-incident

# 500 건수
grep -c ' 500 ' data/access.log

# IP별 500
awk '$5 == 500 {print $2}' data/access.log | sort | uniq -c | sort -rn

# 경로별 500
awk '$5 == 500 {print $4}' data/access.log | sort | uniq -c | sort -rn

# app.log ERROR
grep ERROR data/app.log
```

## answer.txt 예시

```
500_count: 9
attacker_ip: 10.0.0.99
top_endpoint: /api/users
root_cause_hint: db connection timeout to db.internal
```

## 실무 후속 조치

1. **단기**: 10.0.0.99 IP rate-limit 또는 WAF block
2. **중기**: db.internal 연결 풀/타임아웃 점검 (시나리오 06 연계)
3. **장기**: 500 rate 알람 + runbook 자동화
