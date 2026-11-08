# 2단계: 상주 번역·키워드 런타임

2026-11-08 구현. DB 작업 소비·재시도·프로필 등록/최초 활성화는 [3단계](text-analysis-worker.md)에 구현했다. 원본 API는 다른 팀원의 4단계다. [API 목록](../api/README.md)과 [신고·매칭 명세](../api/03-lost-reports-matching.md)의 공개 입력·진행 상태 계약을 따른다. 2단계에서는 엔드포인트와 DB 스키마를 추가하지 않았다.

키워드 추출은 사용자 결정으로 [spaCy·WordNet v2](spacy-wordnet-keywords.md)로 변경했다. 아래 실행·스레드 계약은 유지하며 이전 v1 측정은 이력이다.

## 언어 정책

사용자 결정: 한글이 없는 모든 입력은 실제 언어와 관계없이 EN으로 간주하고 번역 없이 키워드를 추출한다. 일본어·중국어·아랍어·프랑스어도 실패로 처리하지 않는다. 한글만 있는 입력은 KO, 한글과 다른 언어의 글자가 함께 있으면 MIXED다. 숫자·공백·기호는 혼합 언어 판정에 포함하지 않는다.

제목과 설명은 별도로 처리한다. 한글이 있는 필드만 번역하며, 영어 제목과 한국어 설명이면 제목은 그대로 보존한다. 비공개 식별 정보·연락처·사진·보관 위치를 입력하지 않는다. 입력 객체는 description(필수, 1~2000자), title(선택, 1~100자)만 받는다. trim·NFKC 후 필드 경계를 가진 canonical JSON으로 source_hash를 생성한다.

미지원 언어를 EN으로 저장한다는 것은 영어 처리 경로를 택한다는 의미다. 해당 언어의 동의어·형태소 분석이나 한국어와의 교차 언어 매칭 품질까지 보장하지 않는다.

## 설치와 모델 준비

Python·pip·스크립트는 기존 backend 컨테이너 /app에서만 실행한다.

```sh
docker compose exec -T -w /app backend python -m pip install -r requirements.txt
docker compose exec -T -w /app backend python -m pip check
docker compose exec -T -w /app backend python -m scripts.prepare_translation_model
docker compose exec -T -w /app backend python -m scripts.prepare_keyword_resources
```

모델: Helsinki-NLP/opus-mt_tiny_kor-eng. 고정 모델/토크나이저 commit은 `755c263bce01f7b1aa9472b32940961fa1efccf3`이다. 준비 스크립트만 네트워크를 사용하며 config·safetensors·SentencePiece·어휘·생성 설정의 SHA-256을 assets.json에 기록한다. 모델 파일은 공유 `.cache/text-analysis/`에 두고 Git에 포함하지 않는다. 모델 준비 중이거나 준비 전 앱 시작 실패 후에는 준비를 완료하고 기존 backend를 재시작한다.

실행 중에는 local_files_only, trust_remote_code=False, safetensors만 사용하고 기록되지 않은 파일·변조·누락을 거부한다. 런타임이 요청 중 모델을 다운로드하지 않는다. 새 이미지에도 같은 requirements를 설치하되 모델 캐시는 별도 준비해야 한다.

## 앱 수명과 설정

FastAPI lifespan이 전용 ThreadPoolExecutor(max_workers=1)를 만들고 같은 스레드에서 모델 로딩·워밍업·추론·해제를 수행한다. CPU float32, PyTorch CPU 스레드 1개가 기본이다. torch.set_num_threads는 프로세스 전체 PyTorch 연산에 영향을 준다. 모델은 요청마다 로딩하지 않으며 Uvicorn 프로세스마다 1개다. 운영은 worker 1개 기준이고 개발 --reload에서는 프로세스 재시작마다 다시 로딩한다.

| 환경변수 | 기본값 | 역할 |
| --- | --- | --- |
| TEXT_ANALYSIS_ENABLED | true | false이면 명시적으로 비활성화 |
| TEXT_ANALYSIS_MODEL_DIR | /app/.cache/text-analysis | 준비된 assets.json 및 모델 파일 경로 |
| TEXT_ANALYSIS_TIMEOUT_SECONDS | 30 | 분석 전체 제한 시간, 양수·최대300 |
| TEXT_ANALYSIS_CPU_THREADS | 1 | PyTorch CPU 스레드 수, 1~8 |
| TEXT_ANALYSIS_NLP_DIR | /app/.cache/text-analysis-nlp | 준비한 WordNet corpus 경로. spaCy 모델은 고정 패키지로 설치 |

이 값은 backend 프로세스 환경에 전달해야 한다. 상위 Compose가 해당 환경변수를 전달하지 않는다면 루트 .env에만 추가해서는 반영되지 않는다. 이번 변경에서 상위 Compose 파일은 수정하지 않았다.

모델 활성화 시 준비 실패는 앱 startup 실패다. disabled는 READY로 표시하지 않는다. 공개 루트 응답은 기존 형태를 유지하며 준비 상태 확인용 공개 API를 추가하지 않았다. 내부 값은 app.state.text_analysis_state(DISABLED/STARTING/READY/FAILED/STOPPING/STOPPED), app.state.text_analysis_runtime이다. 환경설정·모델 오류가 있어도 성공처럼 시작하지 않는다.

기본 startup 제한은120초, 종료 대기는10초다. 종료는 신규 추론을 거절하고 stop event를 통해 토큰 생성 중단을 요청한다. Python 스레드의 강제 종료는 불가능하므로 네이티브 연산이 멈추지 않으면 close()는 false를 반환하고 상태를 STOPPING으로 남긴다. 프로세스 종료 유예 시간은 운영 supervisor가 관리해야 한다.

## 내부 결과 계약과 실행 제어

```python
from library.text_analysis_types import AnalysisInput

# DB 트랜잭션 밖의 3단계 작업 처리기에서 호출한다.
result = await app.state.text_analysis_runtime.analyze(
    AnalysisInput(description=public_description, title=public_title),
)
```

AnalysisResult는 source_language, source_hash, translated_text, keywords(tuple), attributes(dict), profile_fingerprint를 제공한다. translated_text는 title/description 경계를 보존한 JSON 문자열이며 title이 없는 신고는 null이다. 원본 해시와 번역 결과는 일반 로그·outbox에 기록하지 않는다.

추론 중 다른 요청은 ANALYSIS_BUSY(retryable)로 반환하고 executor에 무제한 제출하지 않는다. 대기·재시도는 3단계 DB 큐가 담당한다. await 취소나 타임아웃 이후에도 실제 future를 추적하여 이전 추론이 끝나기 전에 다음 작업을 받지 않는다. 오류는 코드와 retryable만 전달하고 원문·라이브러리 예외 내용을 노출하지 않는다.

주요 오류: INVALID_TEXT_INPUT, MODEL_ASSETS_INVALID, MODEL_LOAD_FAILED, MODEL_STARTUP_TIMEOUT, MODEL_NOT_READY, ANALYSIS_BUSY, ANALYSIS_TIMEOUT, ANALYSIS_STOPPED, TEXT_CHUNK_LIMIT, TRANSLATION_OUTPUT_LIMIT, TRANSLATION_EMPTY, ANALYSIS_FAILED. 3단계가 코드별 재시도·종료 상태를 DB와 연결해야 한다.

## 긴 입력과 키워드

모델의 256토큰 위치 한도를 준수하고 문장 단위로 묶되 긴 문장은 토큰 단위로 나눈다. 영문 출력의 토큰 증가 여유를 위해 입력은 기본128토큰을 사용한다. 특수 토큰을 포함해 한도를 계산하며 입력을 조용히 자르지 않는다. 필드당 최대32개 조각, 출력은 조각당 최대255토큰이다. EOS 미도달 또는 출력 한도 도달은 실패로 처리하며 강제 EOS로 잘림을 성공처럼 처리하지 않는다. 양쪽 필드는 전체 분석 제한 시간을 공유한다.

생성은 sampling 없이 beam=1이다. 키워드는 spaCy의 표제어·명사구·품사와 WordNet의 단일 synset으로 생성한다. lemma/phrase/wn/identifier/number/term 키를 구분하고 정렬·중복 제거한다. 원문 고유명사·영숫자 식별자·숫자 각인은 번역에서 누락돼도 보조 보존한다. 영문 의존 관계로 부정 특징을 분리하고 긍정 일치에서 제외한다. 자세한 의미 선택·부정·fallback 및 제한은 [v2 설계](spacy-wordnet-keywords.md)를 따른다.

library/data/text_keyword_rules.json은 단어 사전이 아닌 부정·구간·synset 정책만 담는다. 모델 commit, 의존성·spaCy 모델·WordNet 버전, NLP 데이터 해시, 생성 설정, 입력/언어/키워드 버전, 정책 파일과 구현 코드의 해시를 profile fingerprint에 포함한다. runtime.profile은 복사본을 반환한다. DB 등록·matching policy 활성화는 하지 않는다. 규칙 변경 시 기존 프로필을 수정하지 말고 새 프로필을 생성해야 한다.

## 검증과 평가 명령

```sh
docker compose exec -T -w /app backend python -m scripts.evaluate_text_analysis --repeats 3
docker compose exec -T -w /app -e RUN_REAL_TEXT_ANALYSIS_TESTS=true backend python -m scripts.test_backend
```

평가에는 합성 한국어·영어·혼합·미지원 언어·브랜드·숫자·부정·긴 입력을 사용한다. 기본 산출물은 `.cache/text-analysis-evaluation.json`과 `.cache/text-analysis-evaluation-profile.json`이다. 입력은 운영 DB에서 읽지 않는다. 모델 실제 번역 결과·누락 특징·반복 일관성·전체/번역 경로 지연·RSS를 보고한다. 이 작은 고정 세트의 키워드 재현율은 서비스 전체의 매칭 정확도가 아니다.

단위 테스트는 언어 fallback·해시 경계·키워드/부정·실패·취소/타임아웃·중복 추론 차단을 확인한다. 실제 모델 테스트는 고정 assets와 offline 설정으로 실행하고 로딩 횟수·별도 스레드·반복 일관성·토큰 분할·잘림 오류·lifespan 해제를 확인한다. 일반 테스트는 모델을 비활성화하며 실제 모델 테스트는 위 환경변수로 명시 실행한다.

확인된 품질 한계: 합성 문장 “검은색 가죽 지갑입니다.”를 “It's a black wallet.”로 번역하면서 leather가 누락됐다. 같은 문장을150회 반복한 스트레스 입력은 출력 한도에 도달하여 TRANSLATION_OUTPUT_LIMIT으로 거절되며 평가에서 expected_error로 명시한다. 이 사례를 성공 번역이나 예상치 못한 오류0건에 숨기지 않고 expected_rejections로 별도 보고한다. 자연스러운 긴 설명은 성공했다. 입력 분할이 모든 원문 토큰을 전달해도 모델이 모든 속성을 보존한다는 보장은 없다. 현재 작은 사전과 단순 부정 규칙의 정밀도도 후속 실사용 평가가 필요하다. 이미지 재빌드와 실제 운영 부하는 아직 검증하지 않았다.

## 2026-11-08 v1 측정 이력

ARM64·Python3.11 기존 backend 컨테이너에서 합성19사례를 평가했다. 정상18사례는 각3회 동일했고 출력 한도 스트레스1사례는 예상대로 거절됐다. 예상치 못한 실행 오류0건, 기대 키워드 재현율97.5%(leather 누락1건)였다. 로딩·워밍업 약2.25초, 번역 경로 p50 약0.073초·p95 약0.776초, 로딩 후 RSS 약539MiB·평가 후 약541MiB였다. 영어/미지원 언어 우회 경로가 포함된 전체 p50은 번역 성능으로 해석하지 않는다. 이 수치는 작은 합성 세트의 단일 실행 관측이며 처리량/SLO나 실제 서비스 정확도 보장이 아니다.

최종 검증: 실제 모델 테스트를 활성화한 전체392개 테스트가 통과했다(skip 없음). pip check는 충돌 없음이며 git diff --check도 통과했다. 실행 중 backend의 기존 루트 응답200을 확인했다. 모델 준비·평가·테스트는 기존 backend 컨테이너에서 수행했고 DB 테스트는 별도 kaifind_test_translation_20261108을 사용했다. DB 스키마·개발 데이터·4단계 라우터/서비스는 변경하지 않았다.
