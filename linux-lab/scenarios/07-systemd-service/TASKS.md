# シナリオ 07: systemctl サービス障害（WSL / 実 Linux 向け）

## 実務背景

デプロイ後 **lab-web.service が起動しない**。  
`systemctl status` で failed と表示される典型的な障害です。

> **注意:** Cursor Cloud VM では systemctl は動きません。  
> **WSL2（systemd 有効）** または実 Linux で実施してください。  
> 手順: [WSL-SETUP.md](../../WSL-SETUP.md)

## 症状

```bash
systemctl --user status lab-web
# ● lab-web.service - Lab Web Service
#      Active: failed
```

- `incident.txt` 参照
- ユニットファイルの **ExecStart パスが誤っている**

## ミッション

1. `systemctl --user status lab-web` で状態確認
2. `journalctl --user -u lab-web -n 10` でエラー確認
3. `lab-web.service` の **ExecStart** を正しい `bin/web.sh` パスに修正
4. 以下を実行:

```bash
systemctl --user daemon-reload
systemctl --user start lab-web
systemctl --user status lab-web
```

5. `Active: active (running)` を確認

## 初期セットアップ（壊した状態を作る）

```bash
cd /workspace/linux-lab   # または ~/Linux
./install-wsl-service.sh
```

## ヒント

```bash
cd scenarios/07-systemd-service

cat incident.txt
cat lab-web.service
cat bin/web.sh

# 正しいパス例（ホームに合わせて変更）
# ExecStart=/home/あなたのユーザー/Linux/scenarios/07-systemd-service/bin/web.sh

systemctl --user cat lab-web
journalctl --user -u lab-web --no-pager
```

## 完了確認

```bash
cd /workspace/linux-lab
./check.sh 07
```

## 実務との関連

- `systemctl start/stop/restart/status`
- `journalctl -u <service>`
- ユニットファイル修正後は必ず `daemon-reload`
- 本番は `sudo systemctl`（root）— 演習は `--user` で安全に

## 解答

[SOLUTION.md](SOLUTION.md)
