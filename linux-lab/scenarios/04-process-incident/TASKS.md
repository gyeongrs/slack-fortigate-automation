# シナリオ 04: CPU 100% — runaway プロセス

## 実務背景

Web サーバー **CPU 100%** アラーム。バッチ/ループプロセスが応答を妨げています。

## 症状

- システムが遅い
- `incident.txt` 参照
- `bin/runaway.sh` — CPU 消費の無限ループ（意図的）

## ミッション

1. CPU 使用上位プロセスを確認（`ps`, `top`）
2. `runaway.sh` の **PID** を特定
3. プロセスを **終了**（`kill`）
4. 終了を確認（`pgrep` または `ps`）

## ヒント

```bash
cd /workspace/linux-lab/scenarios/04-process-incident

# CPU 順ソート
ps aux --sort=-%cpu | head -10

# runaway を探す
pgrep -af runaway

# PID ファイル参照
cat runaway.pid

# 終了
kill $(cat runaway.pid)
# または
pkill -f runaway.sh
```

## 完了確認

```bash
cd /workspace/linux-lab
./check.sh 04
```

## 実務との関連

- `kill -15` (SIGTERM) → 待機 → `kill -9` (SIGKILL)
- systemd: `systemctl stop`, `Restart=on-failure`
- CPU limit: cgroups, ulimit

## 解答

[SOLUTION.md](SOLUTION.md)
