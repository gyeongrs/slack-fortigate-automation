# Linux 実践トレーニング Lab

運用（Ops）現場でよく遭遇する問題を **シナリオベース** で練習する環境です。
Take Control なしで **Terminal タブ** からすぐ始められます。

## クイックスタート

```bash
cd /workspace/linux-lab
./setup.sh          # 演習環境の初期化（障害状態を生成）
./check.sh          # 全シナリオの採点（解決前/後）
./check.sh 03       # 特定シナリオのみ採点
```

## 学習ロードマップ

| # | シナリオ | 実務イシュー | 主要コマンド |
|---|---------|-------------|-------------|
| 01 | [ログ分析障害](scenarios/01-log-incident/TASKS.md) | 500 エラー急増、攻撃 IP 追跡 | `grep`, `awk`, `sort`, `uniq` |
| 02 | [権限問題](scenarios/02-permissions/TASKS.md) | スクリプト実行不可、設定漏洩 | `chmod`, `chown`, `ls -l` |
| 03 | [ディスク不足](scenarios/03-disk-full/TASKS.md) | ログでディスク Full | `du`, `find`, `gzip`, `df` |
| 04 | [プロセス障害](scenarios/04-process-incident/TASKS.md) | CPU 100% プロセス | `ps`, `top`, `kill` |
| 05 | [cron バックアップ失敗](scenarios/05-cron-failure/TASKS.md) | バックアップ未実行 | `crontab`, `grep`, ログ分析 |
| 06 | [サービス接続失敗](scenarios/06-service-down/TASKS.md) | DB 接続不可 | `ss`, `curl`, 設定ファイル |

## 推奨学習順序

```
1日目: 01 ログ分析  →  grep/awk パイプライン
2日目: 02 権限       →  chmod/chown
3日目: 03 ディスク   →  du/find/df
4日目: 04 プロセス   →  ps/kill
5日目: 05 cron       →  スケジュール・バックアップ
6日目: 06 サービス   →  ポート・設定・接続
```

## 演習の進め方

1. `scenarios/XX-*/TASKS.md` を読み **症状** を把握する
2. Linux コマンドで **原因調査 → 解決** を進める
3. `./check.sh XX` で合格判定を確認する
4. 詰まったら `SOLUTION.md` を参照（まず自分で解いてみてください）

## ディレクトリ構成

```
linux-lab/
├── setup.sh              # 全シナリオの初期化
├── check.sh              # 自動採点
├── scenarios/
│   ├── 01-log-incident/
│   ├── 02-permissions/
│   ├── 03-disk-full/
│   ├── 04-process-incident/
│   ├── 05-cron-failure/
│   └── 06-service-down/
└── shared/               # 共通サンプルデータ
```

## エージェントと一緒に練習する

チャットでの例：

- 「01番シナリオのヒントだけください」
- 「`access.log` で 500 エラー IP Top 3 を出すコマンドを教えて」
- 「実行結果を解説してください: ...」

コマンド実行はエージェントに依頼するか、Terminal タブで直接入力してください。
