# KAIFind API 명세

Notion 최신 문서를 Markdown으로 내보낸 사본입니다. 인증을 포함한 총 63개 엔드포인트의 설계 초안이며, 상세 동작·모델·JSON 예시를 유지했습니다.

내보낸 날짜: 2026-11-02 (KST)

원문: [KAIFind / API](https://app.notion.com/p/40c23542cf8c80b3bc5bd3ccf4aaf232?pvs=204)

| 문서 | 엔드포인트 수 |
| --- | ---: |
| [공통 규칙·운영 요구사항](00-common.md) | — |
| [인증](01-auth.md) | 5 |
| [습득물·검색·사진](02-found-items.md) | 15 |
| [분실 신고·매칭](03-lost-reports-matching.md) | 7 |
| [프로필·알림·키워드 구독](04-profile-notifications.md) | 9 |
| [수거·분쟁·메시지](05-collection-disputes-messages.md) | 9 |
| [관리자](06-admin.md) | 18 |
| [SRS 대조 검토 결과](07-srs-review.md) | — |

문서 간 링크는 로컬 Markdown 파일로 연결했습니다. 목업 SSO는 승인된 범위 변경이며, 미정 정책은 설계 제안으로 구분되어 있습니다. 명세 검토는 실제 구현·성능·보안 테스트 완료를 뜻하지 않습니다.


DB 설계: [DB 스키마 초안](../db/README.md) — 테이블·관계·제약·인덱스·트랜잭션·보존 정책.

2026-11-09 키워드 구독 구현: [키워드 구독 상세 설계](../design/keyword-subscriptions.md) — KEYWORD-01~03과 등록 스냅샷·분석·알림을 연결했다(revision 20261109_0010). 기존 substring 제안을 단어 특징 전체 포함으로 대체했다. 습득물 등록 HTTP API는 별도 범위이며 DB INSERT 트리거로 이벤트를 생성한다.

2026-11-09 설계: [Notification API](../design/notification-api.md) — NOTI-01~04의 설정·목록·읽음 처리, 이벤트 중복 방지와 이메일 전달 통합. 기존 공개 계약을 유지하며 구현 완료를 뜻하지 않는다.

2026-11-09 구현: NOTI-01~04 엔드포인트의 설정 저장·목록·읽음 처리를 연결했다. 알림 이벤트 생산과 이메일 전달·한도·요약은 후속 과제다.

2026-11-09 이메일 구현: [이메일 전달·환경변수](../design/notification-delivery.md)의 환경변수·날짜 정책·가변 슬롯·digest·복구를 mock 제공자로 연결했다(revision 20261109_0009). 매칭 최초 후보와 수거/만료 상태 변경 이벤트를 처리한다. 키워드 생산자는 revision 20261109_0010에 연결했으며 실제 외부 발송은 후속 범위다. 운영 설정은 [README](../../README.md)를 따른다.

2026-11-08 변경: [번역·키워드 비동기 매칭 구현 계획·API 팀 인계](../design/translation-keyword-implementation-plan.md). 물품·신고의 진행 상태, 후보 목록 완전성, 수거 대기 오류와 본문 없는 쓰기 계약을 관련 명세에 반영했다. 4단계 원본 API는 별도 팀원이 담당하며 공통 계약 구현과 기능 API 구현 완료를 구분한다.

2단계 [번역 런타임](../design/translation-runtime.md)을 구현했다. 사용자 결정으로 한글 없는 미지원 언어도 EN으로 간주하고 그대로 키워드를 추출한다. 상주 런타임은 준비됐으며 DB 작업 처리·매칭/원본 API 연결은 후속 단계다.

키워드 추출·비교는 [spaCy·WordNet v2](../design/spacy-wordnet-keywords.md)를 따른다. 수동 분류 사전 대신 표제어·명사구·단일 synset을 사용하며 기존 프로필과 혼용하지 않는다.

3단계 [분석 작업 처리·복구](../design/text-analysis-worker.md)를 구현했다. 활성 정책은 명시적으로 초기화하며 분석 활성 환경에서 정책 누락·모델 불일치는 startup 실패다. 원본 API 연결·전체 매칭 상태 집계·후보 계산은 후속 단계다. 관리자 감사에 TEXT_ANALYSIS_RETRIED와 eventId metadata를 추가했다.

5단계 [matching API·generation 소비자](../design/matching-api.md)를 구현했다. MATCH-01과 비교 범위 진행 상태 집계, 최신 후보 판정·중복 억제·lease 복구를 제공한다. 관리자 감사에 MATCH_EVALUATION_RETRIED를 추가했다(revision 20261108_0008). 4단계 원본 서비스 연결 및 6단계 알림·수거 통합은 별도다.

2026-11-09 DB 백업: [운영 안내](../design/database-backups.md).
매일 04:00 KST·기존 MinIO·7일 보관을 BACKUP_* 환경변수로 설정한다.
공개 API 변경은 없다. revision 20261109_0012에서 습득물 EXPIRED·분실 신고 CLOSED 처리와
삭제·감사·알림을 연결하고 만료 검사 완료 후 백업을 실행한다.
[일일 만료 안내](../design/daily-expiry.md). 분실 신고 원본 HTTP API의 501 구현은 별도 범위다.

2026-11-13 분실 신고: [LOST-01~06 구현](../design/lost-reports.md)을 연결했다.
기존 요청·응답과 매칭 계약을 유지하며 등록·수정·연장에 분석/재평가를 연결한다.
분실 신고 원본 HTTP API의 기존 501 표기는 이 구현으로 대체한다.
