# シナリオ 07 — 解説

## 原因

`lab-web.service` の `ExecStart` が存在しないパスを指している。

## 修正手順

```bash
LAB_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$LAB_ROOT/scenarios/07-systemd-service"

# 1. ユニットファイルを編集
nano lab-web.service
# ExecStart= を以下に修正（実際の絶対パスに置き換え）
# ExecStart=FULL_PATH/bin/web.sh

# 2. ユーザーサービスに再インストール
mkdir -p ~/.config/systemd/user
cp lab-web.service ~/.config/systemd/user/
chmod +x bin/web.sh

# 3. 起動
systemctl --user daemon-reload
systemctl --user start lab-web
systemctl --user status lab-web
```

## ExecStart の正しい例

```ini
[Unit]
Description=Lab Web Service for training
After=network.target

[Service]
Type=simple
ExecStart=/home/ubuntu/Linux/scenarios/07-systemd-service/bin/web.sh
Restart=on-failure

[Install]
WantedBy=default.target
```

`which` や `pwd` で絶対パスを確認:

```bash
realpath bin/web.sh
```

## ログ確認

```bash
journalctl --user -u lab-web -f
```

## 片付け

```bash
systemctl --user stop lab-web
systemctl --user disable lab-web
rm -f ~/.config/systemd/user/lab-web.service
systemctl --user daemon-reload
```
