# 사진 API 및 MinIO

PHOTO-01~03을 구현했다. 원본 파일은 메모리에서 검증·정제한 뒤 폐기하며,
MinIO 비공개 버킷에는 JPEG/PNG/WebP 정제본만 저장한다. DB에는 객체 키와 메타데이터,
사진 연결 관계, 단기 링크 토큰의 SHA-256 해시를 저장한다. 클라이언트에는 객체 키를 노출하지 않는다.

## 실행 설정

기존 환경에 Pillow를 포함한 requirements.txt 의존성을 설치하고 마이그레이션을 적용한다.

```sh
docker compose exec -T backend python -m pip install -r requirements.txt
docker compose exec -T backend python -m alembic upgrade head
```

백엔드 환경변수 예시다. 실제 키를 저장소에 커밋하지 않는다.

```dotenv
# Compose 내부에서는 storage:9000, 호스트 실행 시 localhost:9000
MINIO_ENDPOINT=storage:9000
MINIO_ACCESS_KEY=<애플리케이션 접근 키>
MINIO_SECRET_KEY=<애플리케이션 비밀 키>
MINIO_BUCKET=kaifind-photos
MINIO_SECURE=false
PHOTO_PUBLIC_BASE_URL=http://localhost:8000
PHOTO_MAX_BYTES=10485760
PHOTO_MAX_PIXELS=24000000
PHOTO_UNATTACHED_SECONDS=86400
PHOTO_LINK_SECONDS=60
```

`MINIO_ENDPOINT`는 스킴·경로 없는 호스트:포트다. TLS 환경은 `MINIO_SECURE=true`로
설정하며 생략 시에도 true다. 외부 서비스 주소는 HTTPS여야 하고,
`PHOTO_PUBLIC_BASE_URL`을 실제 서비스 origin으로 설정한다. Host 헤더로 링크를 구성하지 않는다.
프로덕션은 버킷의 객체 읽기·쓰기·삭제 권한을 가진 전용 접근 키를 사용한다.
버킷 생성·정책 확인은 별도 배포 권한으로 실행한다.

기존 Compose의 `storage` 서비스를 사용하며 backend에 MinIO·사진 환경변수를 전달한다.
로컬에서 접근 키를 생략하면 서버의 `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD`를 사용한다.
운영에서는 전용 접근 키를 명시한다. storage의 `/data`는 `storage-data` 영구 볼륨에 저장한다.

버킷이 없다면 버킷 생성·정책 조회 권한을 가진 자격증명으로 다음 명령을 실행한다.
이미 비공개 버킷이 준비되어 있다면 실행할 필요 없다. 이 명령은 기존 정책을 자동 변경하지 않는다.

```sh
docker compose exec -T backend python -m service.photo_storage_setup
```

개발 명령과 테스트는 backend 컨테이너 안에서 실행한다. 운영 DB 마이그레이션은 별도 배포 절차다.

## API 동작

- `POST /api/v1/photos`: 로그인·CSRF·Origin 검사 후 multipart `file`, `purpose`만 받는다.
  원본 파일명·요청 MIME을 신뢰하지 않고 실제 포맷을 확인한다. 용량은 입력·정제본 모두 제한하며,
  chunked 요청도 전체 크기를 제한한다. 원본 multipart 파일은 디스크에 spool하지 않는다.
  이미지 최대 픽셀 수를 확인하고 애니메이션은 거절한다. EXIF 방향을 적용한 뒤 픽셀만
  새 이미지로 재인코딩하므로 GPS·EXIF·ICC·텍스트 메타데이터를 보관하지 않는다.
- `POST /api/v1/photos/{photoId}/access-url`: 요청 본문 없이 호출한다. 공개 비민감 사진도
  익명 또는 로그인 CSRF 세션이 필요하다. 예측 불가능한 256비트 토큰을 생성하고 DB 해시로
  검증한다. 미연결 사진은 업로더만 접근하며 만료 후 접근할 수 없다.
- `GET /api/v1/photo-access/{accessToken}`: 만료·현재 권한을 재검사한다. 민감·보관·미연결
  사진과 보호 상태에서 발급된 링크는 발급 로그인 세션에 결합한다. 공개 링크는 쿠키 없이
  소비할 수 있다. 숨김 물품은 작성자·관리자만, 삭제된 물품은 모두 404다.
  과거 보관사진과 보호 라벨도 유지한다. 제거된 일반 물품사진은 업로더·관리자만 접근한다.
  민감사진은 링크 발급과 실제 조회를 각각 감사하며, 실제 조회 감사의 DB 커밋이 성공한 뒤에만
  이미지 바이트를 응답한다. HEAD/Range는 405, 조건부 요청에도 304 대신 재검사한 200을 반환한다.

사진 응답·오류에 `Cache-Control: private, no-store`, `Referrer-Policy: no-referrer`,
`X-Content-Type-Options: nosniff`를 설정한다. Uvicorn 접근 로그는 토큰 경로를 마스킹한다.
리버스 프록시·APM에서도 `/api/v1/photo-access/` 뒤 토큰을 수집하지 않도록 설정해야 한다.
MinIO 공개 URL·presigned URL로 사진 API를 우회하지 않는다.

주요 오류는 413 `PHOTO_TOO_LARGE`, 422 `INVALID_IMAGE`, 410 `PHOTO_LINK_EXPIRED`,
503 `PHOTO_STORAGE_UNAVAILABLE`이며 공통 JSON 오류 모델을 사용한다.
DB에서 정리된 토큰과 미등록 토큰은 404다.

## 장애 복구와 정리

업로드는 MinIO 쓰기 전에 `photo_upload_intents`를 독립 트랜잭션으로 커밋하고,
해당 intent를 잠근 채 업로드한다. 성공 시 사진 생성과 intent 삭제를 함께 커밋한다.
실패 시 커밋된 사진이 없는지 확인하고 객체를 삭제한다. 보상 삭제 실패나 프로세스 종료 시
남은 intent가 객체 키를 보존하므로 후속 정리에서 회수할 수 있다.
사진은 단일 PUT으로 저장해 프로세스 종료 시 미완료 multipart 조각이 남지 않도록 한다.

```sh
docker compose exec -T backend python -m service.photo_cleanup
```

위 명령을 스케줄러에서 주기적으로 실행한다. 기본 실행은 종류별 최대 100개를 처리하므로
적체가 생기지 않도록 실행 빈도·배치 크기를 운영 규모에 맞춘다. 1시간이 지난 intent,
만료된 미연결 사진, 만료 링크를 정리한다. 처리 중인 intent·사진은 `SKIP LOCKED`로 건너뛰며,
MinIO 삭제 실패 시 DB 행을 보존해 재실행으로 복구한다. 출력은 처리 개수이며 실패가 있으면
종료 코드 1을 반환한다. 연결 이력이 있는 사진은 미연결 정리 대상에서 제외한다.

`service/photo_attachments.py`는 습득물 서비스가 같은 DB 트랜잭션에서 사용할 연결 함수를
제공한다. 물품→사진 순서로 잠그고 업로더·목적·만료·중복 연결을 검사한다. 연결 성공 시
미연결 만료 시각을 지우고 민감 보호 라벨을 기록한다. 습득물 등록·수정 API는 여전히 501이며,
사진 개수 1~5개와 전체 교체는 해당 API 구현 시 이 함수를 이용해 적용해야 한다.
물품 종료 후 1년이 지난 연결 사진의 삭제는 물품 보존 기간 정리 작업에 통합할 후속 범위다.

## 검증

실행 방법과 검증 범위는 [테스트 문서](../tests/README.md)를 참고한다.
이미지 처리는 [Pillow Image 공식 문서](https://pillow.readthedocs.io/en/stable/reference/Image.html)의
디코딩·픽셀 수 보호 동작을 기준으로 구현했다.
