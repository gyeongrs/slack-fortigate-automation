# シナリオ 04 — 解説

```bash
cd /workspace/linux-lab/scenarios/04-process-incident

ps aux --sort=-%cpu | head -5
pgrep -af runaway

kill $(cat runaway.pid)
sleep 1
pgrep -af runaway || echo "終了済み"
```

## kill の手順（実務）

```bash
kill -15 <PID>      # graceful
sleep 5
kill -9 <PID>       # 強制（最終手段）
```

## 再発防止

- systemd `TimeoutStopSec`
- cron/監視でゾンビプロセスのアラーム
