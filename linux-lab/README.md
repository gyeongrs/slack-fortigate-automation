# Linux 実践トレーニング Lab

運用（Ops）現場の問題を **シナリオベース** で練習します。  
**全 7 シナリオは Cursor Cloud の Terminal タブだけで完結** します（WSL・管理者権限不要）。

## クイックスタート（Cloud）

```bash
cd /workspace/linux-lab
chmod +x setup.sh check.sh
./setup.sh
./check.sh
cat scenarios/01-log-incident/TASKS.md
```

> エージェント入力欄で **Cloud** を選択 → 右パネル **Terminal** タブ

---

## 学習ロードマップ（すべて Cloud ✅）

| # | シナリオ | 実務イシュー | 主要コマンド |
|---|---------|-------------|-------------|
| 01 | [ログ分析](scenarios/01-log-incident/TASKS.md) | 500 エラー急増 | `grep`, `awk` |
| 02 | [権限](scenarios/02-permissions/TASKS.md) | 実行不可・漏洩 | `chmod` |
| 03 | [ディスク](scenarios/03-disk-full/TASKS.md) | ログで Full | `du`, `find` |
| 04 | [プロセス](scenarios/04-process-incident/TASKS.md) | CPU 100% | `ps`, `kill` |
| 05 | [cron](scenarios/05-cron-failure/TASKS.md) | バックアップ失敗 | `crontab`, ログ |
| 06 | [DB 接続](scenarios/06-service-down/TASKS.md) | Connection refused | `ss`, `curl` |
| 07 | [サービス復旧](scenarios/07-service-recovery/TASKS.md) | Web 起動失敗 | `svc-manage.sh`, `ss` |

07番は **systemctl の代わり** に `svc-manage.sh` を使います（Cloud で動作）。

---

## 推奨順序

```
1日目: 01  2日目: 02  3日目: 03  4日目: 04
5日目: 05  6日目: 06  7日目: 07
```

---

## 他の人に渡す（Cloud 前提）

1. GitHub / ZIP で `linux-lab` を共有
2. **Cursor 個人アカウント** + **Cloud** で開く
3. `./setup.sh` から開始

管理者権限・WSL・有料以外の方法 → [SHARE.md](SHARE.md)

---

## ディレクトリ

```
linux-lab/
├── setup.sh / check.sh
├── SHARE.md              # 共有・無料プラン向け
└── scenarios/01〜07/
```
