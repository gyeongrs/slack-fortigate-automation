# WSL で Linux Lab + systemctl 実習ガイド

Cursor Cloud では `systemctl` が動きません。**Windows + WSL2** なら無料で同じ演習 + **07番 systemctl** ができます。

---

## 全体の流れ

```
Windows PC
  └── WSL2 (Ubuntu)  ← ここで linux-lab + systemctl
        └── Cursor でフォルダを開く（任意）
```

---

## STEP 1: WSL2 をインストール（1回だけ）

**PowerShell を管理者として実行:**

```powershell
wsl --install
```

PC を再起動 → 「Ubuntu」が起動したらユーザー名とパスワードを設定。

すでに WSL がある場合:

```powershell
wsl --list --verbose
wsl --update
```

---

## STEP 2: systemd を有効化（systemctl に必須）

WSL の Ubuntu で:

```bash
sudo tee /etc/wsl.conf > /dev/null << 'EOF'
[boot]
systemd=true
EOF
```

**PowerShell** で WSL を再起動:

```powershell
wsl --shutdown
wsl
```

確認:

```bash
systemctl --version
systemctl status
# → Running と出れば OK
```

---

## STEP 3: プロジェクトを取得

### 方法 A: GitHub から clone

```bash
cd ~
git clone https://github.com/gyeongrs/Linux.git
cd Linux
```

まだ空の場合:

```bash
git clone -b cursor/linux-practice-lab-b696 \
  https://github.com/gyeongrs/slack-fortigate-automation.git
cd slack-fortigate-automation/linux-lab
```

### 方法 B: ZIP を使う

1. ブラウザで ZIP をダウンロード（Drive 等）
2. WSL で:

```bash
cd ~
unzip ~/Downloads/Linux-upload.zip -d linux-lab
cd linux-lab
```

---

## STEP 4: 演習環境の初期化

```bash
chmod +x setup.sh check.sh install-wsl-service.sh
./setup.sh
./check.sh
```

---

## STEP 5: 01番から順に（Cloud と同じ）

```bash
cat scenarios/01-log-incident/TASKS.md
cd scenarios/01-log-incident
grep ' 500 ' data/access.log

cd ~/Linux   # または linux-lab のパス
./check.sh 01
```

---

## STEP 7: systemctl 実習（WSL のみ）

```bash
cat scenarios/07-systemd-service/TASKS.md
./install-wsl-service.sh    # 壊れた状態でユーザーサービス登録
# TASKS.md の手順で修正 → systemctl --user start lab-web
./check.sh 07
```

### よく使う systemctl コマンド

```bash
systemctl --user status lab-web
systemctl --user start lab-web
systemctl --user stop lab-web
systemctl --user restart lab-web
systemctl --user enable lab-web
journalctl --user -u lab-web -n 20
```

---

## Cursor で WSL を開く（任意）

1. Cursor インストール
2. **Remote - WSL** 拡張（あれば）または **File → Open Folder**
3. パス: `\\wsl$\Ubuntu\home\<ユーザー名>\Linux`

ターミナルは WSL の bash になります（Cloud 不要）。

---

## 他の人に渡すとき（無料・ドメインログイン不要）

1. **Linux-upload.zip** を Google Drive / メールで送る
2. この **WSL-SETUP.md** を一緒に送る
3. 相手は Windows + WSL だけで完結（Cursor 有料不要）

---

## トラブルシューティング

| 問題 | 対処 |
|------|------|
| `systemctl: command not found` | `sudo apt update && sudo apt install -y systemd` |
| `not been booted with systemd` | STEP 2 の `wsl.conf` + `wsl --shutdown` |
| `setup.sh: Permission denied` | `chmod +x setup.sh check.sh` |
| 日本語が文字化け | `export LANG=en_US.UTF-8` |

---

## 学習順序（7日）

```
1日目: 01 ログ分析
2日目: 02 権限
3日目: 03 ディスク
4日目: 04 プロセス
5日目: 05 cron
6日目: 06 サービス (ss/ポート)
7日目: 07 systemctl  ← WSL のみ
```
