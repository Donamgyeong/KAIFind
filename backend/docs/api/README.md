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

2026-11-08 변경: [번역·키워드 비동기 매칭 구현 계획·API 팀 인계](../design/translation-keyword-implementation-plan.md). 물품·신고의 진행 상태, 후보 목록 완전성, 수거 대기 오류와 본문 없는 쓰기 계약을 관련 명세에 반영했다. 4단계 원본 API는 별도 팀원이 담당하며 공통 계약 구현과 기능 API 구현 완료를 구분한다.
