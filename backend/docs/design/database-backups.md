# PostgreSQL 일일 백업

기존 backend의 전용 스레드에서 PostgreSQL 17 `pg_dump -Fc`를 실행하고 기존 MinIO의
비공개 전용 버킷에 저장한다. 공개 HTTP API는 추가하지 않는다. 사진과 역할·tablespace 같은
클러스터 전역 객체는 덤프 대상이 아니며 복구 환경에서 역할·확장을 사전 준비한다.

## 설정·적용

백업 설정은 backend 상위 프로젝트 루트 `.env`에서 관리하며 예시는 같은 루트 `example.env`를 따른다. Compose 기본 정책은
매일 04:00 Asia/Seoul, 7일 보관, 활성화다. 라이브러리 기본 활성화는 false여서
Compose 이외의 실행에서는 BACKUP_ENABLED=true를 명시해야 한다.

| 환경변수 | 기본값 | 의미 |
| --- | --- | --- |
| BACKUP_ENABLED | Compose true / 코드 false | 자동 백업 활성화 |
| BACKUP_TIME | 04:00 | HH:MM 작업 시작 시각 |
| BACKUP_TIMEZONE | Asia/Seoul | IANA 시간대 |
| BACKUP_MINIO_BUCKET | kaifind-db-backups | 사진 버킷과 다른 비공개 전용 버킷 |
| BACKUP_MINIO_PREFIX | postgres/ | 상대 객체 경로 |
| BACKUP_RETENTION_DAYS | 7 | 업로드 시각부터 보관할 일수 |
| BACKUP_POLL_SECONDS | 30 | 시각·재시도 확인 주기 |
| BACKUP_TIMEOUT_SECONDS | 1800 | pg_dump 및 아카이브 목록 검사 각각의 제한 시간 |
| BACKUP_MAX_ATTEMPTS | 3 | 날짜당 최초 실행 포함 최대 시도 횟수 |
| BACKUP_RETRY_SECONDS | 60,300 | 각 실패 후 대기 초; 재시도 수 이상의 값 필요 |
| BACKUP_CATCH_UP_ENABLED | true | 시작 시 이미 지난 당일 작업 한 번 보충 |

접속은 기존 DATABASE_URL과 MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/SECURE를 사용한다.
자격증명은 명령행 인수나 로그에 기록하지 않는다. DB SSL 접속 옵션도 pg_dump 환경에 전달한다.
환경변수 변경은 backend 재생성 이후 적용한다. 시각·보관 정책은 재시작 직후 적용되며
이미 성공한 날짜는 설정을 바꾸어도 다시 덤프하지 않는다. 미래 시도부터 새 재시도 정책을 사용한다.

새 환경에서는 다음 순서로 적용한다. 기존 DB·MinIO 볼륨을 보존하고 backend만 재생성한다.

```sh
docker compose build backend
docker compose exec -T -w /app backend python -m alembic upgrade head
docker compose up -d --no-deps backend
docker compose exec -T -w /app backend python -m scripts.manage_backups status
```

## 실행·실패·보관

DB 세션 advisory lock으로 자동·수동 실행을 직렬화한다. 날짜별 database_backups 이력은
revision 20261109_0011에 추가했다. 서버가 내려간 과거 날짜의 덤프를 소급 생성하지 않는다.
당일 04:00 이후 시작하면 보충하고, 그 이전에는 정각을 기다린다. 보충을 끄면 시작 시각보다
앞선 당일 일정은 건너뛴다. 시간대 변경으로 같은 날짜가 되풀이되어도 날짜당 성공은 한 번이다.

임시 디렉터리는 소유자 전용 권한이며 완료·실패 시 제거한다. pg_dump 종료와 pg_restore --list를
확인한 후 SHA-256을 계산해 객체 metadata에 기록한다. MinIO 업로드 뒤 크기·metadata를 조회하고
성공을 기록한다. 파일 내용 전체 체크섬 검증은 복원 시 내려받은 파일에 대해 수행한다.
객체 키는 `<prefix><DB 이름 SHA-256 앞 16자>/<일정 날짜>.dump`다.

MinIO 저장 직후 프로세스가 종료돼도 같은 객체의 metadata로 성공을 재조정하며 중복 덤프하지 않는다.
잠금이 해제된 RUNNING 상태는 중단된 시도로 취급한다. 횟수를 소진하면 해당 날짜는 FAILED로
남고 다음 날 일정은 정상 진행한다. 로그 BACKUP_FAILED 및 status 명령으로 실패를 확인한다.
BACKUP_WORKER_CYCLE_FAILED는 DB·버킷 접근이나 보관 정리 실패 점검 대상이다. 외부 경보 전송은 없다.

사진 버킷과 같은 버킷, 접근 정책이 존재하는 버킷, versioning이 Enabled/Suspended인 버킷은
거부한다. 새 전용 버킷은 접근 정책 없이 생성한다. 버전 객체를 남겨 보관 기간을 우회하지 않도록
전용 버킷의 versioning은 사용하지 않는다. bucket lifecycle은 자동 변경하지 않는다.

당일 백업 성공 후, 이후 주기마다 해당 DB 경로의 .dump 객체 중 MinIO last_modified 기준
7일 이상 지난 객체를 삭제한다. 새 백업이 계속 실패하면 오래된 성공본은 보존하므로 보관 기간은
장애 중 늘어날 수 있다. 복구 뒤 다음 성공 시 정리한다. 정리 실패는 이미 성공한 덤프 상태를
FAILED로 바꾸지 않는다. 업로드 중 장애의 미완료 multipart는 MinIO 운영 정리 대상이다.
이력은 파일 삭제 후에도 남으며 보관 정책은 백업 객체에 적용한다.

```sh
# 자동 백업 활성 여부와 관계없이 오늘 백업을 즉시 실행; 성공 날짜는 재사용
# 실패 재실행도 날짜당 최대 횟수를 준수한다.
docker compose exec -T -w /app backend python -m scripts.manage_backups run
docker compose exec -T -w /app backend python -m scripts.manage_backups status
```

backend 종료 시 실행 중인 작업을 기다린다. 강제 종료되면 DB 잠금은 해제되고 다음 시작 때
위 절차로 재조정한다. 작업 중 배포 시 충분한 종료 유예 시간을 확보한다.

## 명세와 남은 연동

API README 및 00-common의 DB 백업 규칙을 확인했다. 현재 일일 만료 검사 스케줄러가 없어
**만료 검사 완료 → 백업 순서 연동은 아직 미구현**이다. 이번 기능은 독립 백업이며 해당 SRS
전체 완료를 뜻하지 않는다. 추후 일일 만료 작업 완료를 확인한 뒤 본 서비스를 호출해야 한다.

기존 MinIO에 저장하므로 동일 호스트·볼륨 장애에 대비한 외부 사본은 없다. MinIO 사진 자체의
백업도 별도다. 개인정보가 포함된 덤프는 접근을 제한하고 저장소 암호화·키 관리는 운영 환경에서
마련한다. 현재 애플리케이션 수준 암호화는 추가하지 않는다.

## 복원·검증

실제 자동 검증:

```sh
docker compose exec -T -w /app backend python -m scripts.test_backend tests/test_database_backup.py -q
```

테스트는 기존 db 서비스 안에 kaifind_test_backup_*/kaifind_test_restore_* DB와 기존 storage에
kaifind-test-backup-* 버킷만 임시 생성·삭제한다. 실제 덤프 → MinIO → 다운로드 → SHA-256 비교 →
pg_restore --exit-on-error --no-owner --no-acl로 별도 DB 복원 → 데이터 확인을 수행한다.
보관 경계·재시도 한도·동시 잠금·업로드 후 중단 복구·버킷 공개 차단도 검증한다.

운영 복원은 서비스·이메일 워커를 정지한 격리 환경에서 수행한다. status의 object_key로 파일을
내려받아 sha256과 비교하고, 필요한 역할·확장을 준비한 빈 DB에 pg_restore --exit-on-error로
복원한다. 개발/운영 DB를 검증 대상으로 덮어쓰지 않는다. 복원된 backup 이력은 덤프 시작 시점의
RUNNING 상태일 수 있으며 객체 metadata와 재조정된다.

서비스 재개 전에 종료·보존 만료 정리를 적용하고, 백업 후 발생한 삭제·수신 거부와 이메일 발송
이력을 별도 최신 기록과 대조해야 한다. 현재 이 최신 기록의 외부 보존 및 자동 재적용은
구현하지 않았으므로 실제 운영 재개에는 수동 복구 절차가 필요하다. 단순 복원 테스트 통과를
삭제 데이터 재노출 방지나 운영 복구 훈련 완료로 간주하지 않는다.
