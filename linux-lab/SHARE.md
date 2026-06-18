# 共有ガイド（Cloud 前提）

## 相手に必要なもの

| 項目 | 必須？ |
|------|--------|
| Cursor（個人メール登録） | ✅ |
| Cloud Agent | ✅（有料 or 体験） |
| Windows 管理者権限 | ❌ |
| WSL / Linux インストール | ❌ |
| 会社ドメインログイン | ❌ |

---

## 相手の手順（3ステップ）

```
1. Cursor インストール → https://cursor.com
2. Clone from GitHub:
   https://github.com/gyeongrs/slack-fortigate-automation.git
   ブランチ: cursor/linux-practice-lab-b696
   フォルダ: linux-lab/
3. Cloud 選択 → Terminal:
   cd linux-lab && ./setup.sh
```

---

## ZIP で渡す場合

Raw URL:
```
https://github.com/gyeongrs/slack-fortigate-automation/raw/cursor/linux-practice-lab-b696/linux-lab/Linux-upload.zip
```

相手: ZIP 解凍 → Cursor でフォルダを開く → Cloud → `./setup.sh`

---

## 無料プランの場合

Cloud Agent が使えない場合は **GitHub Codespaces**（ブラウザ）でも 01〜07 可能:

1. リポジトリ → Code → Codespaces → Create
2. ターミナルで `cd linux-lab && ./setup.sh`

---

## 送るメッセージ例

```
Linux 演習プロジェクトです。

1. Cursor を入れる（個人メールで OK）
2. このリポジトリを Clone
3. エージェントで「Cloud」を選ぶ
4. Terminal で:
   cd linux-lab
   ./setup.sh
   cat scenarios/01-log-incident/TASKS.md

WSL も管理者権限も不要です。
```
