# Linux 実践トレーニング Lab

運用（Ops）現場でよく遭遇する問題を **シナリオベース** で練習する環境です。

## どの環境で使う？

| 環境 | 01〜06 | 07 systemctl |
|------|--------|--------------|
| **Cursor Cloud** | ✅ | ❌ |
| **WSL2 (Windows)** | ✅ | ✅ [WSL-SETUP.md](WSL-SETUP.md) |
| **Mac / Linux** | ✅ | ✅ |

**無料で全部やる:** Windows + WSL2 + ZIP（Cursor 有料不要）

---

## クイックスタート

```bash
chmod +x setup.sh check.sh
./setup.sh
./check.sh
```

**WSL + systemctl:** [WSL-SETUP.md](WSL-SETUP.md) を読んでから `./install-wsl-service.sh`

---

## 学習ロードマップ

| # | シナリオ | 実務イシュー | 主要コマンド |
|---|---------|-------------|-------------|
| 01 | [ログ分析障害](scenarios/01-log-incident/TASKS.md) | 500 エラー急増 | `grep`, `awk` |
| 02 | [権限問題](scenarios/02-permissions/TASKS.md) | 実行不可・漏洩 | `chmod` |
| 03 | [ディスク不足](scenarios/03-disk-full/TASKS.md) | ログで Full | `du`, `find` |
| 04 | [プロセス障害](scenarios/04-process-incident/TASKS.md) | CPU 100% | `ps`, `kill` |
| 05 | [cron 失敗](scenarios/05-cron-failure/TASKS.md) | バックアップ未実行 | `crontab` |
| 06 | [接続失敗](scenarios/06-service-down/TASKS.md) | DB 接続不可 | `ss` |
| 07 | [systemctl](scenarios/07-systemd-service/TASKS.md) | サービス failed | `systemctl`, `journalctl` |

---

## 推奨学習順序

```
1〜6日目: 01〜06（Cloud / WSL どちらでも）
7日目:   07 systemctl（WSL 推奨）
```

---

## 他の人に渡す（無料）

1. `Linux-upload.zip` を Google Drive 等で共有
2. **WSL-SETUP.md** を一緒に送る
3. 相手: `wsl --install` → ZIP 解凍 → `./setup.sh`

---

## ディレクトリ構成

```
linux-lab/
├── WSL-SETUP.md          # WSL セットアップ（重要）
├── install-wsl-service.sh # 07番用
├── setup.sh / check.sh
└── scenarios/01〜07/
```
