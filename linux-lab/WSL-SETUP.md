# WSL 向け（任意・上級）

**通常は Cloud だけで全シナリオ完了できます。** このファイルは自宅 PC で WSL を使いたい人向けです。

Cloud で 07番は `svc-manage.sh` を使用（`scenarios/07-service-recovery/`）。

WSL で本物の `systemctl` を練習する場合のみ:

1. `wsl --install`（管理者権限が必要）
2. `/etc/wsl.conf` に `[boot] systemd=true`
3. `wsl --shutdown` 後に再起動

詳細は省略。Cloud 利用を推奨します。
