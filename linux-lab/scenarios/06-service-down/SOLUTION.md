# 시나리오 06 — 해설

## 방법 A: Python mock (권장 — nc 없어도 됨)

```bash
cd /workspace/linux-lab/scenarios/06-service-down

python3 << 'PY' &
import socket, time
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
s.bind(("0.0.0.0", 5432))
s.listen(5)
print("mock db listening on 5432", flush=True)
while True:
    c, addr = s.accept()
    c.close()
PY

sleep 1
ss -tln | grep 5432
```

## 방법 B: mock-server.sh (nc 필요)

```bash
sudo apt install -y netcat-openbsd   # 필요 시
nohup ./mock-server.sh > /tmp/mock-db.log 2>&1 &
ss -tln | grep 5432
```

## hosts (선택)

```bash
# db.internal 이름 해석 (sudo 필요할 수 있음)
echo "127.0.0.1 db.internal" | sudo tee -a /etc/hosts
getent hosts db.internal
```

## 트러블슈팅 순서 (실무)

1. 앱 설정 (host/port)
2. DNS/hosts
3. 포트 리스닝 (`ss -tlnp`)
4. 로컬 연결 (`nc -zv host port`)
5. 방화벽/ACL
6. DB 서비스 로그
