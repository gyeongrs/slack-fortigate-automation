# シナリオ 01 — 解説

## 正解サマリー

| 項目 | 値 |
|------|-----|
| 500 エラー件数 | 9件 |
| 主犯 IP | 10.0.0.99 |
| 最多 500 パス | /api/users |
| app.log の原因 | db connection timeout |

## コマンド例

```bash
cd /workspace/linux-lab/scenarios/01-log-incident

# 500 件数
grep -c ' 500 ' data/access.log

# IP 別 500
awk '$5 == 500 {print $2}' data/access.log | sort | uniq -c | sort -rn

# パス別 500
awk '$5 == 500 {print $4}' data/access.log | sort | uniq -c | sort -rn

# app.log ERROR
grep ERROR data/app.log
```

## answer.txt 例

```
500_count: 9
attacker_ip: 10.0.0.99
top_endpoint: /api/users
root_cause_hint: db connection timeout to db.internal
```

## 実務のフォローアップ

1. **短期**: 10.0.0.99 IP の rate-limit または WAF block
2. **中期**: db.internal 接続プール/タイムアウト点検（シナリオ 06 と連携）
3. **長期**: 500 rate アラーム + runbook 自動化
