# シナリオ 03: ディスク不足（ログで /var/log Full）

## 実務背景

ディスク使用率 **85% 超** アラーム。`/var/log` 配下の大容量ログが原因です。

## 症状

- `var/log/disk-alert.txt` アラームファイルあり
- `var/log/` 配下に **5MB ログ** が多数
- 古い `archive/` バックアップログが蓄積

## ミッション

1. `var/log/` で **1MB 以上のファイル** 一覧を確認（`find` または `du`）
2. 大容量 `.log.1`, `.log.2` を **削除または gzip 圧縮**
3. `archive/` 内の **30日以上前のログ** を整理（演習用: `backup-2026-01~03.log` 削除）
4. 整理後、1MB 超ファイルが **0 件** であることを確認

## ヒント

```bash
cd /workspace/linux-lab/scenarios/03-disk-full

du -sh var/log/*
du -ah var/log/ | sort -rh | head -10

find var/log -type f -size +1M -ls
find var/log -type f -size +1M -exec gzip {} \;
# または
find var/log -type f -size +1M -delete
```

## 完了確認

```bash
cd /workspace/linux-lab
./check.sh 03
```

## 実務との関連

- logrotate 設定の点検
- `/var/log` 専用パーティション
- アラーム: 80% warn、90% critical

## 解答

[SOLUTION.md](SOLUTION.md)
