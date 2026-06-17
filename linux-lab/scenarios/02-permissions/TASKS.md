# 시나리오 02: 권한 문제 (배포 스크립트 실행 불가)

## 실무 배경

배포 담당자가 **deploy.sh 실행 실패** 및 **보안 감사에서 db.env 노출** 지적을 받았습니다.

## 증상

```bash
./app/bin/deploy.sh
# bash: ./app/bin/deploy.sh: Permission denied
```

- `app/config/db.env` — DB 비밀번호 포함, 권한 과다
- `app/data/` — world-writable (777)

## 미션

1. `deploy.sh`가 **실행되도록** 권한 수정
2. `db.env`를 **소유자만 읽기(600)** 로 변경
3. `app/data/`를 **750** 으로 변경 (그룹 읽기/실행, others 차단)
4. `./app/bin/deploy.sh` 실행 후 "Deploy OK" 출력 확인

## 힌트

```bash
cd /workspace/linux-lab/scenarios/02-permissions

ls -la app/bin/deploy.sh
ls -la app/config/db.env
ls -lad app/data/

stat -c '%a %n' app/bin/deploy.sh app/config/db.env app/data/
```

## 완료 확인

```bash
cd /workspace/linux-lab
./check.sh 02
```

## 실무 연결

- `.env`, API 키: 600 또는 640, root 소유
- 실행 스크립트: 750
- 데이터 디렉터리: 750/770, others 금지

## 정답

[SOLUTION.md](SOLUTION.md)
