# 3단계: 분석 요청·outbox 소비·복구

2026-11-08 구현. [API 목록](../api/README.md), [공통 계약](../api/00-common.md),
[습득물](../api/02-found-items.md), [신고·매칭](../api/03-lost-reports-matching.md),
[수거](../api/05-collection-disputes-messages.md), [관리자 감사](../api/06-admin.md)를 대조했다.
기존 엔드포인트·인가·요청/응답 모델은 유지한다. 분석 상태와 내부 작업 처리를 구현하며,
원본 API 연결은 4단계, 비교 범위 matchingStatus 집계·후보 계산은 5단계다.

## 초기 준비와 활성 정책

기존 backend 컨테이너의 /app에서 수행한다. 모델·spaCy·WordNet은 2단계 안내대로 준비한다.

```sh
docker compose exec -T -w /app backend python -m alembic upgrade head
docker compose exec -T -w /app backend python -m scripts.manage_text_analysis initialize
```

initialize는 실제 모델을 로딩한 뒤 runtime.profile의 fingerprint를 재계산하고 프로필과 정책을
멱등 등록한다. 정책은 카테고리 동일, 발견일의 KST 날짜 >= lostDateFrom,
건물 OR canonical 키워드이며 lostDateTo 상한을 추가하지 않는다.
최초 matching_runtime 행만 생성하며 이미 활성화된 다른 정책을 교체하지 않는다.
프로필 이름은 전체 fingerprint로 생성한다. 내용이 다른 프로필·정책을 UPDATE하지 않는다.

분석 활성화 환경에서 앱은 모델 준비 후 활성 정책·프로필의 무결성과 실제 모델의 일치 여부를
확인하고 워커를 시작한다. 정책 누락은 MATCHING_POLICY_NOT_CONFIGURED,
불일치는 ANALYSIS_PROFILE_MISMATCH로 startup을 실패시킨다. 임의 프로필·가짜 READY·원본만
저장하는 fallback은 없다. 초기화 후 backend를 재시작한다. TEXT_ANALYSIS_ENABLED=false는
일반 API 테스트와 명시적인 분석 비활성 환경용이며 분석 요청 함수의 정책 검증은 우회하지 않는다.

프로필 교체는 유지보수 모드에서 비활성 프로필 backfill·정책 전환·전체 재평가 후 쓰기를 재개하는
기존 설계를 따른다. 이 명령은 정책 교체나 무중단 전환을 수행하지 않는다. 후보 계산이 없는
3단계만으로 정책 전환의 재평가 완료를 선언할 수 없다.

## 4단계 호출 계약

service/text_analysis.py가 아래 함수를 제공한다.

```python
async def request_found_item_analysis(db, *, item, now): ...
async def request_lost_report_analysis(db, *, report, now): ...
async def request_item_reevaluation(db, *, item, now): ...
async def request_report_reevaluation(db, *, report, now): ...
async def analysis_status(db, *, owner): ...
```

호출자는 트랜잭션과 카테고리 잠금을 소유하며 원본 저장·flush 후 트리거가 만든 text_version을
읽어 전달한다. 서비스는 commit하거나 모델을 호출하지 않는다. 분석 함수는 현재 분석 ORM 행,
재평가 함수는 작업 UUID를 반환한다. 삭제 물품·종료/기한 만료 신고에는 신규 작업을 만들지 않고
None을 반환한다. 원본 종료·개인정보 삭제는 원본 서비스 책임이다.

분석 유일 키는 (원본, profile_id, text_version), outbox 유일 키는 (feature ID, 1, event type)이다.
READY·FAILED를 중복 요청으로 초기화하지 않는다. 재평가 요청은 같은 행의 generation을 증가시키고
기존 lease·claimed_generation·completed_generation을 유지한다. 새 요청은 실패 표시를 해제한다.
분석 완료도 자기 원본의 재평가를 요청하며 후보나 알림은 생성하지 않는다.

analysis_status는 읽기만 수행하며 현재 분석의 공개 상태를 반환한다. 누락·SUPERSEDED는 PENDING으로
표현하고 작업을 생성하지 않는다. 종료 신고는 정책 변경 후에도 마지막 보존 분석 상태를 읽는다.
matchingStatus나 isComplete를 이 함수의 READY만으로 결정하면 안 된다.

## 소비·저장·실패

service/outbox_worker.py의 AnalysisWorker는 기존 프로세스의 비동기 작업이다. 새 컨테이너나
메모리 작업 큐는 없다. 두 분석 event type만 확보하며 알림·스토리지 이벤트를 소비하지 않는다.
기본 폴링 1초, lease 60초, heartbeat 20초, 최대 시도 5회다.

1. 짧은 SKIP LOCKED 트랜잭션으로 작업 하나의 attempts와 새 lease token을 저장한다.
2. 카테고리 → 원본 → 분석 → outbox 순서로 잠그고 입력을 복사한다.
3. 모든 DB 트랜잭션을 종료한 뒤 공개 title/description만 모델에 전달한다.
4. 같은 잠금 순서로 현재 원본·text_version·해시·활성 프로필·lease를 재검증한다.
5. READY 결과·재평가 요청·outbox processed_at을 원자적으로 커밋한다.

작업 조회·갱신은 종료 여부와 token·만료를 검사하며 최종 트랜잭션에서도 lease 만료 시 롤백한다.
heartbeat는 별도 세션을 사용한다. 카테고리가 최초 조회와 잠금 사이에 달라지면 전체 트랜잭션을
중단하고 재시도한다. 추론 중 일반 version만 바뀌고 text_version이 같으면 결과를 재사용한다.
오래된 입력은 SUPERSEDED, 소멸한 대상은 취소 처리한다. 논리 삭제 트리거가 제거한 결과를 복원하지 않는다.

retryable 오류는 최대 300초의 지수 백오프와 jitter로 재시도한다. 한도 초과·영구 오류는 분석 FAILED와
outbox failed_at을 함께 저장한다. processed_at으로 실패를 숨기지 않는다. 예상하지 못한 오류는
ANALYSIS_FAILED 또는 TEXT_ANALYSIS_WORKER_CYCLE_FAILED 코드만 기록한다. DB 오류로 처리하지 못한 작업은
lease 만료 후 다시 확보한다. 타임아웃 이후 실제 추론 future가 끝나기 전에는 다음 작업을 확보하지 않는다.
종료 시 신규 확보를 멈추고 워커에 10초 유예 후 취소·롤백하며 런타임을 닫는다.
원문·번역문·키워드와 라이브러리 예외 문자열을 일반 로그·outbox에 복제하지 않는다.

## 정합성 복구와 수동 재시도

```sh
docker compose exec -T -w /app backend python -m scripts.manage_text_analysis repair
docker compose exec -T -w /app backend python -m scripts.manage_text_analysis retry <event-uuid>
```

repair는 UUID keyset 100개 단위 트랜잭션으로 현재 적격 원본의 누락 분석·outbox를 보완한다.
이미 READY이거나 실패한 작업을 무조건 재실행하지 않는다. 만료된 PROCESSING lease는 소비자가 복구한다.
변경된 입력의 과거 대기 작업은 소비 시 SUPERSEDED로 종료한다. 자동 주기 실행은 추가하지 않았다.

retry는 실패한 분석 이벤트만 받는다. 현재 입력이면 같은 이벤트의 attempts를 0으로 초기화하고
분석을 PENDING으로 바꾼다. 이전 입력·프로필이면 과거 작업을 취소하고 최신 작업을 보장한다.
원본 잠금과 같은 트랜잭션에서 SYSTEM/TEXT_ANALYSIS_RETRIED 감사를 남기며 대상 ID와 eventId만 기록한다.
회원용 재시도 엔드포인트는 추가하지 않는다.

DB revision 20261108_0007은 감사 action·metadata 허용 목록만 확장한다. 기존 기록을 변경하지 않는다.
재시도 감사가 존재하면 downgrade를 거절해 이력을 삭제·변조하지 않는다. 왕복 테스트는 전용 임시 DB에서 수행한다.

## 검증 범위

실제 PostgreSQL에서 요청 중복·롤백, lease 동시 확보·만료·늦은 성공/실패, heartbeat,
추론 중 입력 변경·논리 삭제·신고 종료·일반 버전 변경, generation 보존, 실패·수동 복구·누락 보완을 검사한다.
실제 모델 → DB READY → 재평가 요청까지의 통합 테스트와 lifespan의 정책 확인·실패·종료를 포함한다.
원본 HTTP API 연결, 후보 비교·알림·수거 최신성, 운영 부하·이미지 재빌드는 후속 검증이다.

2026-11-08 검증 결과: 실제 모델 활성 전체 426개 테스트가 skip 없이 통과했다. 이후 카테고리 이동과
잠금 직전 이동 경합 2개를 추가하고 대상 테스트 19개가 통과했다(실제 모델 1개는 앞선 전체 실행에서 검증).
pip check·alembic check·git diff --check도 통과했다. 개발 DB에 revision 0007과 최초 활성 정책을 적용했으며
기존 테이블 행 수 보존과 backend 재시작 후 루트 200 응답을 확인했다.
