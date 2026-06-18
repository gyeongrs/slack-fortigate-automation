# WAF 演習 01: SQL インジェクション検知

## 目的

ModSecurity CRS が **攻撃的なリクエストをブロック** するのを確認します。

## 前提

```bash
cd /workspace/linux-lab/waf-lab
./start.sh
```

ブラウザ: Cloud Agent の **Browser タブ** または Take Control で  
http://127.0.0.1:8080 を開く

---

## 実習 1: 正常アクセス

```bash
curl -I http://127.0.0.1:8080/
# → HTTP 200 または 302
```

## 実習 2: SQLi 風ペイロード（ブロック確認）

```bash
curl -v "http://127.0.0.1:8080/rest/products/search?q=' OR 1=1--"
# → HTTP 403 Forbidden を期待
```

## 実習 3: XSS 風ペイロード

```bash
curl -v "http://127.0.0.1:8080/rest/products/search?q=<script>alert(1)</script>"
# → 多くの場合 403
```

## 実習 4: WAF ログ確認

```bash
sudo docker compose logs waf --tail=50
# ModSecurity の rule id を探す
```

---

## 採点

```bash
./check.sh
```

---

## 学習ポイント

| 項目 | 内容 |
|------|------|
| WAF の位置 | クライアント → **WAF** → アプリ |
| ブロック | 悪性パターン → 403 |
| CRS | OWASP Core Rule Set |
| 運用 | ログの rule_id でチューニング |

## 発展

- `docker-compose.yml` の `PARANOIA` を `2` に変更して再テスト
- False Positive: 正常な検索語がブロックされないか確認
