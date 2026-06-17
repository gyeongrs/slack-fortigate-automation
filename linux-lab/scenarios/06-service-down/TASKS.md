# 시나리오 06: DB 연결 실패 (Connection refused)

## 실무 배경

앱 기동 후 **db.internal:5432 Connection refused**.  
배포 직후 DB 연결 설정 문제로 서비스 down.

## 증상

- `config/app.env`: `DB_HOST=db.internal`, `DB_PORT=5432`
- 5432 포트 **리스닝 없음**
- `hosts.snippet` — `/etc/hosts` 등록 필요 (선택)

## 미션

1. `config/app.env` 설정 확인
2. **5432 포트** 리스닝 여부 확인 (`ss -tln` 또는 `netstat`)
3. `mock-server.sh`를 **백그라운드**로 실행해 DB mock 기동
4. `nc -zv 127.0.0.1 5432` 또는 `ss -tln | grep 5432` 로 연결 확인

## 힌트

```bash
cd /workspace/linux-lab/scenarios/06-service-down

cat config/app.env
cat incident.txt

ss -tln | grep 5432

# mock DB 서버 시작 (openbsd-netcat 필요할 수 있음)
nohup ./mock-server.sh > /tmp/mock-db.log 2>&1 &

# 또는 Python으로 간단 mock
python3 -c "
import socket
s=socket.socket()
s.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
s.bind(('127.0.0.1',5432))
s.listen(1)
print('listening 5432')
import time
time.sleep(3600)
" &

ss -tln | grep 5432
```

## 완료 확인

```bash
cd /workspace/linux-lab
./check.sh 06
```

## 실무 연결

- `telnet/nc` 포트 probe
- DNS: `getent hosts db.internal`
- 방화벽: `iptables -L`, security group
- 앱 로그 + DB 로그 상관 분석

## 정답

[SOLUTION.md](SOLUTION.md)
