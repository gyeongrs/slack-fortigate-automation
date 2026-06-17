# 시나리오 04 — 해설

```bash
cd /workspace/linux-lab/scenarios/04-process-incident

ps aux --sort=-%cpu | head -5
pgrep -af runaway

kill $(cat runaway.pid)
sleep 1
pgrep -af runaway || echo "종료됨"
```

## kill 단계 (실무)

```bash
kill -15 <PID>      # graceful
sleep 5
kill -9 <PID>       # 강제 (최후)
```

## 재발 방지

- systemd `TimeoutStopSec`
- cron/monitoring으로 zombie 프로세스 알람
