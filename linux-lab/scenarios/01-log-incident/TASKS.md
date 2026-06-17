# 시나리오 01: 로그 분석 장애 (INC-2026-0612)

## 실무 배경

09:00경 모니터링 알람: **API 500 에러 급증**.  
온콜 엔지니어로서 로그를 분석하고 incident 보고서 초안을 작성합니다.

## 증상

- `/api/users`, `/api/orders` 응답 지연
- 일부 사용자 500 에러
- `data/incident.txt` 티켓 참고

## 실습 파일

```
data/access.log   ← 웹 접근 로그
data/app.log      ← 애플리케이션 로그
data/incident.txt ← 장애 티켓
```

## 미션

### Level 1 (기본)

1. `access.log`에서 **500 에러 건수**를 센다
2. 500을 발생시킨 **IP 주소**를 찾는다
3. 해당 IP의 **요청 경로 Top 3**를 구한다

### Level 2 (심화)

4. `app.log`에서 **ERROR** 줄만 추출한다
5. access.log 500 시간대와 app.log ERROR 시간대가 **일치하는지** 확인한다
6. `answer.txt`에 아래 형식으로 작성한다:

```
500_count: <숫자>
attacker_ip: <IP>
top_endpoint: <경로>
root_cause_hint: <app.log 기반 추정 원인>
```

## 힌트

```bash
cd /workspace/linux-lab/scenarios/01-log-incident

# 500만 필터
grep ' 500 ' data/access.log

# IP별 집계 (형식: TIMESTAMP IP METHOD PATH STATUS LATENCY)
awk '$5 == 500 {print $2}' data/access.log | sort | uniq -c | sort -rn

# 경로별 집계
awk '$5 == 500 {print $4}' data/access.log | sort | uniq -c | sort -rn
```

## 완료 확인

```bash
cd /workspace/linux-lab
./check.sh 01
```

## 실무 연결

- WAF/방화벽: 공격 IP `10.0.0.99` 차단 정책 검토
- SIEM: 동일 패턴 알람 룰 작성
- Runbook: "500 급증 → access.log IP 집계 → app.log 상관 분석"

## 정답

막히면 [SOLUTION.md](SOLUTION.md) 참고
