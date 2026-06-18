# シナリオ 01: ログ分析障害 (INC-2026-0612)

## 実務背景

09:00頃 モニ**500 エラー急増**タリングアラーム: **API** 。
オンコールエンジニアとしてログを分析し、インシデント報告書の下書きを作成します。

## 症状

- `/api/users`, `/api/orders` の応答遅延
- 一部ユーザーで 500 エラー
- `data/incident.txt` チケット参照

## 演習ファイル

```
data/access.log   ← Web アクセスログ
data/app.log      ← アプリケーションログ
data/incident.txt ← 障害チケット
```

## ミッション

### Level 1（基本）

1. `access.log` で **500 エラー件数** を数える
2. 500 を発生させた **IP アドレス** を特定する
3. その IP の **リクエストパス Top 3** を求める

### Level 2（応用）

1. `app.log` から **ERROR** 行のみ抽出する
2. access.log の 500 発生時刻と app.log の ERROR 時刻が **一致するか** 確認する
3. `answer.txt` に以下の形式で記載する:

```
500_count: <数字>
attacker_ip: <IP>
top_endpoint: <パス>
root_cause_hint: <app.log に基づく推定原因>
```

## ヒント

```bash
cd /workspace/linux-lab/scenarios/01-log-incident

# 500 のみフィルタ
grep ' 500 ' data/access.log

# IP 別集計（形式: TIMESTAMP IP METHOD PATH STATUS LATENCY）
awk '$5 == 500 {print $2}' data/access.log | sort | uniq -c | sort -rn

# パス別集計
awk '$5 == 500 {print $4}' data/access.log | sort | uniq -c | sort -rn
```

## 完了確認

```bash
cd /workspace/linux-lab
./check.sh 01
```

## 実務との関連

- WAF/ファイアウォール: 攻撃 IP `10.0.0.99` のブロックポリシー検討
- SIEM: 同一パターンのアラームルール作成
- Runbook: 「500 急増 → access.log IP 集計 → app.log 相関分析」

## 解答

詰まったら [SOLUTION.md](SOLUTION.md) を参照