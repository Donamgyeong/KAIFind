# 일일 만료 검사와 백업

2026-11-09. API 목차, 공통 운영 요구사항, 습득물 FR-25 및 분실 신고 FR-11을 기준으로 한다.
공개 HTTP API는 추가하지 않는다. 기존 backend 워커가 매일 04:00 Asia/Seoul에
만료 검사 → 완료 기록 → pg_dump → 기존 MinIO 저장 순서로 실행한다.

## 대상·트랜잭션

검사 최초 시작 시각을 cutoff_at으로 고정한다. 재시도는 같은 기준시각을 유지한다.

| 대상 | 조건 | 처리 |
| --- | --- | --- |
| 습득물 | POSTED, deleted_at 없음, expires_at <= cutoff_at | EXPIRED, closed_at=cutoff_at, purge_after=종료 1년 후, 대화·메시지 삭제, 습득자 알림 이벤트, SYSTEM 감사 |
| 분실 신고 | OPEN, expires_at <= cutoff_at | CLOSED, closed_at=cutoff_at, purge_after=종료 1년 후, 비공개 식별 정보 삭제, 대기 이메일 항목 취소, SYSTEM 감사 |

숨김 물품도 만료하며, 직접 보관 물품은 기존 초안의 일반 만료 규칙을 적용한다.
30일은 등록·연장·재게시에서 계산된 expires_at으로 판단하고 새 기간을 다시 계산하지 않는다.
물품·사진·위치·후보 이력을 만료 시 전부 삭제하지 않는다. 1년 보존 후 물리 삭제는 별도 범위다.
2월29일 종료의 1년 후 보존 기한은 기존 one_year_after 정책대로 다음 해2월28일이다.

후보를 잠금 없이 조회한 후 기존 library.matching_lock과 동일한 카테고리 키를 정렬해
잠그고 대상 행을 잠근다. 상태·카테고리·기한·삭제 여부를 재검사한다. 카테고리가 바뀌면
배치를 롤백하고 재시도한다. SKIP LOCKED로 누락 대상을 건너뛰지 않으며, 잠금 시간 초과는
실패로 기록한다. 메시지 전송의 물품 행 잠금 및 DB 상태 트리거와도 직렬화된다.

배치별로 상태·삭제·알림 이벤트·감사·처리 건수를 같은 트랜잭션에서 저장한다.
DB의 기존 item_cleanup, lost_report_cleanup, expiry_notification 트리거를 재사용한다.
만료 감사는 ITEM_STATUS_CHANGED/LOST_REPORT_STATUS_CHANGED와 SYSTEM 행위자만 기록하고
개인정보 본문을 복제하지 않는다. 종료된 신고는 기존 매칭·분석 소비자의 상태 재검사로
신규 알림이 차단되고 대기 이메일은 DB 트리거 취소 및 발송 전 자격 검사로 제외된다.
후보 이력은 보존한다. 모델 분석 자원이 없어도 만료 작업은 실행할 수 있다.

## 이력·재시작·백업

revision 20261109_0012는 daily_expiry_runs 및 database_backups.expiry_run_id를 추가한다.
만료·수동 검사·백업이 같은 DB 세션 advisory lock(73011911)을 공유한다.
날짜별 cutoff_at/run_id, 상태, 시도 횟수, 재시도 시각, 오류 코드와 처리 건수를 보존한다.
배치 중 종료되면 완료된 배치는 유지하며 미처리 대상부터 다음 시도에서 이어 간다.
RUNNING 상태인데 잠금을 다시 얻을 수 있으면 이전 프로세스가 종료된 것으로 취급한다.
중단된 시도도 최대 횟수에 포함한다. 감사·삭제·이벤트가 이미 커밋된 대상은 다시 처리하지 않는다.

만료 실패·재시도 대기·횟수 소진이면 EXPIRY_BLOCKED를 반환하고 백업하지 않는다.
만료 성공 후 백업 실패이면 백업 단계만 재시도한다. 만료 시도와 백업 시도는 별도 한도다.
실패한 전날 덤프를 소급 생성하지 않고 다음 날짜 만료 검사가 남은 기한 경과 대상을 처리한다.

수동 run도 당일 일정으로 기록한다. 04:00 이전에 수동 검사를 완료하면 정기 실행은 해당
cutoff를 재사용하며 이후 만료 대상은 다음 날짜에 처리한다. BACKUP_ENABLED=false는 자동
만료·백업을 함께 중지하며 수동 실행은 허용한다. BACKUP_CATCH_UP_ENABLED 등 일정은 공유한다.

백업 객체는 `<prefix><DB 이름 hash>/<날짜>-<만료 run_id>.dump`에 저장한다.
기존 독립 백업은 expiry_run_id가 없으므로 첫 연동 실행에서 만료 완료 후 새 객체로 한 번
다시 생성한다. 이전 객체는 7일 보관 정리까지 유지한다. 날짜별 백업 이력은 새 객체를 가리킨다.
백업 중 프로세스가 종료되면 같은 run_id 객체 metadata로 기존 백업 복구 절차를 따른다.

## 환경변수·운영

실제 설정은 backend 상위 `.env`, 비밀정보 없는 예시는 상위 `example.env`, 전달은 기존
Compose backend environment에 둔다. backend 안에 별도 env 파일을 만들지 않는다.

| 변수 | 기본값 | 정책 |
| --- | --- | --- |
| EXPIRY_BATCH_SIZE | 100 | 배치 후보 수, 1~10000 |
| EXPIRY_MAX_ATTEMPTS | 3 | 날짜당 최초 포함 최대 시도 수 |
| EXPIRY_RETRY_SECONDS | 60,300 | 실패별 대기 초, 모든 재시도에 양수 간격 필요 |
| EXPIRY_LOCK_TIMEOUT_SECONDS | 10 | 배치의 잠금 대기 한도, 1~300초 |

시각·시간대·보충 실행·폴링은 BACKUP_*를 사용하며 두 개의 일정을 만들지 않는다.
30일 도메인 규칙은 이번 설정으로 변경하지 않는다. 새 설정은 backend 재생성 후 적용한다.

```sh
docker compose exec -T -w /app backend python -m alembic upgrade head
docker compose up -d --no-deps backend
# 당일 만료 검사만 수행; 자동 백업 여부와 무관하게 최대 시도 횟수 준수
docker compose exec -T -w /app backend python -m scripts.manage_expiry run
docker compose exec -T -w /app backend python -m scripts.manage_expiry status
# 만료 완료를 보장한 뒤 백업; status는 만료·백업 이력을 함께 출력
docker compose exec -T -w /app backend python -m scripts.manage_backups run
docker compose exec -T -w /app backend python -m scripts.manage_backups status
```

EXPIRY_FAILED/EXPIRY_ATTEMPTS_EXHAUSTED 및 처리 건수를 운영자가 확인한다. 별도 외부 경보는
전송하지 않는다. 횟수 소진 시 환경변수 한도를 늘려 재시작하면 새 한도 내에서 다시 시도할 수 있다.

## API 경계와 남은 범위

현재 LOST-01~06은 501 플레이스홀더다. 상세·수정·연장 API 전체 구현은 이번에 추가하지 않는다.
library.expiry의 report_is_open/effective_report_status는 GET에서 저장하지 않는 공통 판정이며
기존 이메일·분석 경로에 연결했다. 매칭 조회는 기존 expires_at 검사로 이미 만료 경계를 처리한다.
향후 상세 API는 만료된 신고의 비공개 정보를 제외하고 CLOSED로 투영해야 한다. 수정·연장 API는
같은 카테고리·행 잠금 안에서 기한을 검사해야 하며 이미 CLOSED인 신고를 재개하지 않는다.
실제 HTTP 연장·재게시 API 통합은 해당 API 구현 시 검증해야 한다.

전체 서비스 재개 전 백업 후 삭제 이력 재적용, 1년 보존 정리, 사진 자체 백업은 이 기능이
대체하지 않는다. 기존 MinIO가 같은 호스트에 있으므로 호스트 전체 장애용 외부 사본은 없다.

## 검증

기존 backend /app에서 전용 kaifind_test_* DB와 kaifind-test-* MinIO 버킷으로 실행한다.

```sh
docker compose exec -T -w /app backend python -m scripts.test_backend tests/test_expiry.py tests/test_expiry_migration.py tests/test_database_backup.py -q
```

만료 경계·숨김·삭제·기한 연장·수거 상태 제외, 삭제·감사·이벤트 원자성과 중복 방지,
카테고리 잠금 시간 초과·재시도 한도, 부분 커밋 후 복구, 실제 수거/연장/재게시 상태 변경·메시지
전송과의 DB 경합, 만료 실패 시 백업 차단, 백업 재시도 및 기존 독립 백업 교체를 검증한다.
실제 MinIO 백업을 별도 DB에 복원해 EXPIRED/CLOSED 및 개인정보·메시지 삭제를 확인한다.
마이그레이션 왕복 시 기존 백업 이력을 보존한다.
