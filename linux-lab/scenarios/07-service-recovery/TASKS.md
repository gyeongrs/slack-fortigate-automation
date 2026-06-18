# シナリオ 07: Web サービス起動失敗（Cloud 対応）

## 実務背景

デプロイ後 **lab-web が起動せず**、監視でポート 8088 が down。  
本番では `systemctl` を使いますが、**Cloud 環境では `svc-manage.sh`** で同じ手順を練習します。

## 症状

```bash
./svc-manage.sh start
# ERROR: スクリプトが見つからないか実行不可: /wrong/path/web.sh

./svc-manage.sh status
# ● lab-web — inactive (dead)
```

## ミッション

1. `service.conf` の **SCRIPT_PATH** を確認し、正しい `bin/web.sh` の **絶対パス** に修正
2. `chmod +x bin/web.sh svc-manage.sh`
3. サービス起動:

```bash
./svc-manage.sh start
./svc-manage.sh status
ss -tln | grep 8088
curl -s http://127.0.0.1:8088/
# → lab-web OK
```

4. ログ確認: `./svc-manage.sh logs`

## ヒント

```bash
cd scenarios/07-service-recovery

cat incident.txt
cat service.conf
realpath bin/web.sh

# service.conf の SCRIPT_PATH を realpath の結果に合わせる
nano service.conf
```

## systemctl との対応（参考）

| systemctl | この演習 |
|-----------|---------|
| `systemctl start` | `./svc-manage.sh start` |
| `systemctl status` | `./svc-manage.sh status` |
| `systemctl stop` | `./svc-manage.sh stop` |
| `journalctl -u` | `./svc-manage.sh logs` |
| ユニットファイル修正 | `service.conf` 修正 |

## 完了確認

```bash
cd /workspace/linux-lab
./check.sh 07
```

## 解答

[SOLUTION.md](SOLUTION.md)
