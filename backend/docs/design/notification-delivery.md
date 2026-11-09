# 알림 이벤트·이메일 전달 후속 설계

2026-11-09 KST. 아래는 설계 당시 계약이다. 환경변수 파서·mock 전달 워커·digest·날짜 정책·revision 0009를 구현했다.
실제 외부 발송과 키워드 생산자는 구현하지 않았다. 수거·만료는 DB 상태 변경 outbox로 연결했다.
현재 지원하는 설정은 `notification.env.example`을 따른다. FROM·TEST_RECIPIENT는 실제 제공자용 예약 설계이며 mock에서 사용하지 않는다.
[API 목차](../api/README.md), [알림 API](../api/04-profile-notifications.md),
[기존 설계](notification-api.md), [DB 설계](../db/README.md)를 기준으로 한다.
NOTI-01~04의 공개 계약은 유지한다. 기존 숫자 20통·19통·20시는 아래 환경변수의 기본값으로 바꾼다.

## 설정 계약

배포 환경에서 backend에 전달한다. 호스트 .env에만 선언하고 끝내지 않고 상위 Compose backend의
환경 전달도 구현 시 확인한다. 실제 비밀값이 있는 .env는 수정하거나 버전 관리하지 않는다.

| 환경변수 | 기본값 | 검증·의미 |
| --- | --- | --- |
| NOTIFICATION_EMAIL_ENABLED | false | 엄격한 true/false. false이면 전송·슬롯 예약 중지, 인앱·수신 허용 이메일 의도는 저장 |
| NOTIFICATION_EMAIL_DAILY_LIMIT | 20 | 정수 1 이상. 사용자별 실제 발송일 한도, digest 포함 |
| NOTIFICATION_EMAIL_DIGEST_TIME | 20:00 | 정확한 HH:MM, 00:00~23:59. Asia/Seoul 기준 |
| NOTIFICATION_EMAIL_POLL_SECONDS | 5 | 양수. 전송·digest 실행 여부 확인 주기 |
| NOTIFICATION_EMAIL_LEASE_SECONDS | 120 | 양수. 외부 timeout보다 커야 함 |
| NOTIFICATION_EMAIL_TIMEOUT_SECONDS | 30 | 양수. 제공자 요청 timeout |
| NOTIFICATION_EMAIL_RETRY_SECONDS | 60,300,1800 | 쉼표로 구분한 양의 정수, 오름차순. 이후 마지막 간격으로 반복 |
| NOTIFICATION_EMAIL_RETRY_JITTER_RATIO | 0.2 | 0~1. 재시도 간격에 적용 |
| NOTIFICATION_EMAIL_MAX_ATTEMPTS | 10 | 1 이상. 초과 시 FAILED·운영 경보, 수동 재시도 가능 |
| NOTIFICATION_EMAIL_PROVIDER | mock | mock 또는 구현된 제공자 어댑터 이름. 미지원 값 거부 |
| NOTIFICATION_EMAIL_FROM | 미설정 | 실제 제공자 사용 시 필수 이메일 주소 |
| NOTIFICATION_EMAIL_TEST_RECIPIENT | 미설정 | 목업 계정 외부 발송 시 필수 테스트 수신함. 실제 회원 주소 대신 사용 |
| NOTIFICATION_EMAIL_APP_BASE_URL | 미설정 | 전송 활성 시 필수 HTTPS origin. 링크는 서버의 허용된 상대 경로와 결합 |

시간대는 기존 KST 계약에 따라 Asia/Seoul로 고정한다. 개별 한도는 DAILY_LIMIT-1로 계산하고
별도 환경변수로 중복 정의하지 않는다. limit=1이면 개별 발송 없이 하루 digest만 허용한다.
limit=0은 오류이며 전체 중지는 EMAIL_ENABLED=false를 사용한다.

예시(향후 배포용 예제 설정에 추가):

```dotenv
NOTIFICATION_EMAIL_ENABLED=false
NOTIFICATION_EMAIL_DAILY_LIMIT=20
NOTIFICATION_EMAIL_DIGEST_TIME=20:00
NOTIFICATION_EMAIL_POLL_SECONDS=5
NOTIFICATION_EMAIL_LEASE_SECONDS=120
NOTIFICATION_EMAIL_TIMEOUT_SECONDS=30
NOTIFICATION_EMAIL_RETRY_SECONDS=60,300,1800
NOTIFICATION_EMAIL_RETRY_JITTER_RATIO=0.2
NOTIFICATION_EMAIL_MAX_ATTEMPTS=10
NOTIFICATION_EMAIL_PROVIDER=mock
```

설정은 프로세스 시작 시 읽는다. 잘못된 값은 조용히 기본값으로 대체하지 않고 startup을 실패시킨다.
활성 전송에 필요한 제공자 자격증명은 어댑터 구현 시 별도 환경변수로 정의하며 로그에 남기지 않는다.
HTTP 사용자 요청 속도 제한과 이 이메일 발송량 제한은 독립적이다.

## 날짜별 정책과 설정 변경

환경변수는 원하는 정책이고, 여러 워커가 공유하는 실제 날짜 정책은 DB에서 결정한다.
email_delivery_policies에 delivery_date(KST 날짜 PK), daily_limit, digest_time, created_at을 저장한다.
당일 정책이 없을 때 워커가 전역 advisory lock을 잡고 설정값을 최초 INSERT한다.
이미 존재하면 그날은 저장된 정책을 사용한다. 워커 설정이 다르면 경보를 남기고 해당 정책을 따른다.
당일 한도·시각 변경은 다음 날짜부터 적용하며 미래 날짜 정책은 미리 생성하지 않는다.
배포 시 모든 워커를 같은 설정으로 교체해야 다음 날짜의 최초 생성 경쟁에서도 의도한 값이 적용된다.

이 방식으로 한도를 낮춘 직후 이미 보낸 수보다 한도가 작아지거나 digest가 하루 두 번 실행되는 일을 막는다.
전송 활성/중지와 timeout·재시도 설정은 재시작 후 즉시 적용하며 이미 외부 요청 중인 메일은 회수하지 못한다.

## 예약·발송·digest

1. 도메인 변경과 인앱·이메일 의도 생성은 기존 설계대로 같은 트랜잭션에서 처리한다.
   전송 전역 중지는 사용자 수신 거부와 다르다. 중지 동안 적재된 의도는 재개 후 현재 설정·상태로 재검사한다.
2. 사용자 행 잠금 후 해당 KST 날짜 정책을 읽고 슬롯을 예약한다. 개별은 1~limit-1,
   digest는 limit 슬롯이다. UNIQUE(recipient_id, delivery_date, slot_no)를 유지한다.
3. 예약·전송 중·성공·결과 불명확 상태는 모두 슬롯을 점유한다. 확실히 미전송인 취소/실패도
   초기 구현에서는 그날 슬롯을 재사용하지 않는다. 따라서 한도는 상한이며 반드시 채우는 수는 아니다.
4. 개별 한도 초과분의 digest_on은 아직 마감 전이면 오늘, 마감 시각 이상이면 다음 날이다.
   개별 슬롯이 남으면 digest 시각 이후에도 개별 전송할 수 있다.
5. now>=당일 digest 시각이면 사용자·날짜당 digest를 하나만 만들고, created_at<마감 시각이며
   digest_on<=오늘인 적격 항목을 고정한다. 정확한 시각 일치 조건을 쓰지 않아 재시작 후에도 실행한다.
   빈 digest는 예약하지 않는다. 마감 시각에 생성된 항목은 다음 날 대상이다.
6. 며칠 중단 후 재개하면 지난 날짜마다 메일을 보내지 않는다. 미처리 항목을 현재 날짜의
   다음 가능한 digest에 합치고 실제 발송일 한도만 적용한다. 유효하지 않거나 보존 만료된 항목은 취소한다.
7. 다음 날짜 개별 재시도는 같은 delivery.id로 실제 발송일 슬롯을 다시 예약한다.
   슬롯이 없으면 항목을 digest로 이관할 수 있으나, 제공자가 확실히 미전송임을 확인한 경우에만 허용한다.
   결과 불명확한 메일은 다른 delivery로 편입하지 않고 제공자 상태부터 조회한다.
8. 지난 날짜 digest 재시도와 오늘 digest가 경합하면 실제 발송일의 하나의 digest 슬롯을 사용한다.
   확실한 미전송이면 현재 digest에 항목을 합치고 이전 delivery는 취소한다.
   결과 불명확이면 기존 delivery 확인이 끝날 때까지 새 digest를 발송하지 않는다.

스케줄은 기존 backend lifespan 내부 폴링으로 실행한다. 별도 서비스 컨테이너나 공개 실행 API를 만들지 않는다.
여러 프로세스는 SKIP LOCKED·사용자 잠금·유일 키로 중복 실행을 막는다.
DB 트랜잭션은 짧게 유지하고 외부 요청 전 커밋한다. 전송 직전 사용자 설정·대상 상태를 재검사한다.
메일 언어는 사용자 프로필 언어를 사용하고 payload에 번역 문구·원문을 복사하지 않는다.

## 마이그레이션과 전달 보장

현재 email_deliveries CHECK는 개별 1~19/digest 20으로 고정되어 있어 반드시 교체해야 한다.
새 CHECK는 kind 허용값과 slot_no>=1만 검사한다. 정책별 상한·종류별 슬롯은 잠금 서비스가 검사한다.
사용자·날짜별 digest 유일 partial index도 추가한다. 과거 migration 파일은 수정하지 않는다.

- email_delivery_policies 추가. 기존 발송 날짜는 limit=20, digest_time=20:00으로 backfill한다.
- email_deliveries.lease_token UUID 추가. claim마다 새 token으로 교체하고 완료·실패 저장에 token/lease를 검사한다.
- 결과 불명확을 표현하는 UNKNOWN 상태 및 조회 재시도 경로를 추가한다. UNKNOWN은 새 발송 요청보다 상태 확인을 우선한다.
- 기존 SENT 데이터·delivery ID·슬롯·provider_message_id는 보존한다. 정책 FK는 필요한 날짜를 backfill한 뒤 추가한다.
- 고정 슬롯으로 되돌릴 수 없는 데이터가 생긴 downgrade는 거절한다. 데이터를 삭제하여 downgrade하지 않는다.

제공자 어댑터는 send(idempotency_key=delivery.id), lookup(delivery.id)를 제공한다.
동일 delivery의 재시도는 같은 키를 사용한다. 제공자의 멱등성 보장 기간을 넘긴 UNKNOWN은
자동 재발송하지 않고 운영 확인 대상으로 남긴다. SMTP처럼 조회·멱등성이 없는 어댑터는
결과 불명확 시 중복 없는 자동 복구를 보장할 수 없으므로 초기 실제 발송 제공자 선택 시 이 기능을 확인한다.
네트워크 경계를 넘는 자정에는 정확한 수신 시각을 보장할 수 없다. 한도는 서버가 외부 전송 요청을
시작하는 KST 날짜 기준이며, 자정 직전 최종 날짜 확인 후 달라졌으면 재예약한다.

## 구현 순서·검증

1. library/notification_settings.py에 환경변수 파싱·검증, 앱 startup 연결 및 배포용 예제/Compose 전달을 구현한다.
2. 날짜 정책·슬롯 제약·lease·UNKNOWN migration과 과거 데이터 이행 검증을 구현한다.
3. service/notification_events.py를 매칭·수거·만료 트랜잭션에 연결한다. 각 생산자 상태가 준비된 뒤 연결한다.
4. mock 제공자로 email_worker와 digest·재시도·복구를 구현한 뒤 실제 제공자를 연결한다.
5. 키워드 이벤트는 구독 CRUD·다중 구독 근거와 함께 별도로 통합한다.

검증은 기존 backend /app과 기존 db의 kaifind_test_*에서 수행한다.
설정 누락/오류·limit=1/2/20/50, 시각 00:00/23:59, 당일 정책 변경·워커 설정 차이,
동시 마지막 슬롯·digest 생성, 마감 직전/정각/직후, KST 자정·여러 날 중단·재시작,
다음 날짜 재시도·UNKNOWN·늦은 lease 완료·제공자 성공 후 DB 장애를 검사한다.
API 기존 4개의 회귀, 수신 거부·종료·취소 경합·민감정보 부재와 migration 왕복도 검사한다.
문서 설계 단계에서는 실행 동작을 검증하지 않았다. 실제 제공자 전달·부하·프런트엔드 링크는 통합 검증 대상이다.
