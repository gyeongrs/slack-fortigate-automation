# WAF 演習ラボ（ModSecurity + Juice Shop）

OWASP **Juice Shop**（脆弱な Web アプリ）の前に **ModSecurity CRS** を置き、  
WAF のブロック動作を **Cursor Cloud + Docker** で体験します。

## 必要環境

- Cursor Cloud VM
- Docker（`../start-docker.sh` で起動）

**ローカル Linux / WSL / PowerShell は不要**

---

## クイックスタート

```bash
cd /workspace/linux-lab
./start-docker.sh          # 初回のみ（Docker デーモン起動）

cd waf-lab
chmod +x start.sh stop.sh check.sh
./start.sh                 # 初回はイメージ DL で数分
./check.sh                 # 採点
```

## アクセス

| URL | 説明 |
|-----|------|
| http://127.0.0.1:8080 | **WAF 経由**（演習はここ） |
| Juice Shop 直接 | コンテナ内部のみ（比較用） |

## 演習

1. [01 SQLi テスト](scenarios/01-sqli-test.md)

## 停止

```bash
./stop.sh
```

## 構成

```
クライアント (curl / ブラウザ)
       │
       ▼
┌──────────────────┐
│  WAF (ModSec CRS)│  :8080
│  nginx-alpine    │
└────────┬─────────┘
         ▼
┌──────────────────┐
│  Juice Shop      │  :3000（内部）
│  脆弱 Web アプリ  │
└──────────────────┘
```

## トラブルシューティング

```bash
# ログ
sudo docker compose logs -f waf

# 再起動
./stop.sh && ./start.sh

# Docker デーモン
../start-docker.sh
```

## linux-lab との関係

| ラボ | 内容 |
|------|------|
| `linux-lab/` 01〜07 | Linux 運用（ログ・権限・プロセス等） |
| `waf-lab/` | WAF / Web セキュリティ |

---

## 共有

ZIP / GitHub で `linux-lab` ごと渡せば `waf-lab` も含まれます。  
相手も Cloud + `./start-docker.sh` → `./waf-lab/start.sh`
