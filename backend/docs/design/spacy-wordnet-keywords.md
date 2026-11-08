# spaCy·WordNet 기반 키워드 추출·비교 v2

2026-11-08 사용자 결정에 따른 구현. [API 목록](../api/README.md)·[매칭 명세](../api/03-lost-reports-matching.md)·[런타임](translation-runtime.md)을 확인했다. 기존 카테고리/날짜/건물 OR 키워드 판정·엔드포인트·인가·응답 필드는 유지한다. 공통 키워드 생성 방식과 분석 프로필만 v2로 변경한다. 일반 검색·구독은 범위 밖이다.

## 파이프라인

```text
한국어 포함 필드 → 기존 Marian 영어 번역
한글 없는 필드 → 번역 생략(미지원 언어도 EN으로 가정)
  → spaCy 토큰화·품사·표제어·구문/명사구 분석
  → 명사·고유명사·형용사·수식 분사 및 미등록 단어 보존
  → 품사별 WordNet synset 선택
  → 부정 특징 제거·정렬·중복 제거
  → 동일 프로필 결과의 공통 키워드 비교
```

기존 object/color/material/distinctive 등 수동 단어 분류 사전은 제거했다. text_keyword_rules.json은 부정어·구간 경계·명사구 길이·WordNet 의미 정책만 담고 단어별 aliases는 갖지 않는다. 단복수는 spaCy 표제어로 통합한다. 미등록어는 사전 등록 여부와 관계없이 보존한다.

| 특징 | 키 형식 | 예시 |
| --- | --- | --- |
| 일반 표제어/고유명사 | lemma:... | lemma:dinosaur, lemma:keychain, lemma:sony |
| 명사구 | phrase:... | phrase:purple dinosaur keychain |
| 선택된 동의어 의미 집합 | wn:... | wn:sofa.n.01 |
| 영숫자 모델명 | identifier:... | identifier:wh1000xm5 |
| 숫자 각인 | number:... | number:1234 |
| 비ASCII 원문 fallback | term:... | term:黑色钱包 |

`Purple dinosaur keychains`와 단수 keychain은 동일 표제어·명사구를 만든다. `A sofa`와 `A couch`는 서로 다른 lemma 키를 가지지만 `wn:sofa.n.01`을 공유해 키워드 일치로 판정된다. 브랜드·모델 번호·숫자는 원문에서도 보완한다. 한국어 원문 일반 명사를 보완 경로로 그대로 넣어 번역을 우회하지 않는다.

## spaCy 처리

en_core_web_sm 3.8.0을 사용하며 NER는 제외한다. tok2vec·tagger·parser·attribute_ruler·lemmatizer를 유지한다. 명사·고유명사·형용사를 기본 추출하고 amod/acl로 수식하는 분사 동사는 scratched와 같은 표면형을 유지해 상태 특징을 잃지 않게 한다. 불용어·구두점·일반 동사는 제거하되 WordNet에도 없는 단어와 X 품사·비ASCII 단어는 fallback으로 보존한다.

명사구는 최대6개의 추출 가능한 내용 토큰으로 구성한다. 긴 명사구는 구문 특징만 생략하고 개별 표제어는 유지한다. spaCy의 품사/표제어 추정이 틀릴 가능성이 있으며 모든 미등록어의 활용형까지 완벽히 통합하는 것은 아니다.

## WordNet 정책과 한계

NLTK WordNet 3.0의 영문 synset을 사용한다. 명사(n)·형용사(a)와 수식 분사에 대해 **품사가 일치하는 첫 번째 의미 하나**만 선택한다. 고유명사·미등록어에는 synset을 추정해 넣지 않는다. 같은 synset ID가 공통이면 동의어 근거가 된다. 상위어·하위어·관련어·반의어·재귀 확장은 하지 않는다. dog/cat이 animal을 공유한다는 이유만으로 일치하지 않는다.

첫 번째 의미는 문맥 의미 판별(WSD)이 아니다. 예를 들어 sticker의 첫 명사 의미가 일상적인 접착 스티커와 다를 수 있다. 다의어 오탐과 의미 순위 차이에 따른 누락은 남는다. WordNet에 없는 keychain 같은 단어의 표제어는 보존하지만, 미등록 동의어까지 자동 연결하지는 못한다. 잘못된 모든 의미를 한 번에 확장하는 방식은 사용하지 않는다.

## 부정과 매칭

no/not/without/n't의 대상은 spaCy 의존 관계의 하위 구간으로 결정하고 but/however 뒤는 분리한다. `bag without a strap`은 bag만 긍정 특징이며 strap과 그 synset은 attributes.negated에 둔다. `not red but blue wallet`은 blue/wallet을 유지한다. 부정 범위를 가로지르는 명사구는 긍정 키워드로 사용하지 않는다.

같은 원본의 다른 필드에서 긍정·부정 동의어가 함께 나오면 부정 synset에 속하는 긍정 특징을 보수적으로 제거한다. 영어 분석기이므로 외국어 부정까지 해석하지 않는다.

`library.keyword_matching.common_keywords(left, right)`는 AnalysisResult 두 개를 받아 같은 profile_fingerprint인지 검사하고 키워드 교집합을 정렬해 반환한다. 프로필이 다르면 KEYWORD_PROFILE_MISMATCH로 거절한다. 실제 DB 후보 생성·버전/정책 확인·알림·재평가 서비스는 후속 단계다. 이 함수는 DB·인증·알림 부작용이 없다.

## 자원 준비·상주·버전

```sh
docker compose exec -T -w /app backend python -m pip install -r requirements.txt
docker compose exec -T -w /app backend python -m scripts.prepare_keyword_resources
```

spaCy 모델은 requirements.txt의 고정3.8.0 wheel로 설치한다. WordNet은 nltk_data 저장소의 고정 commit `96f9b3252457a2b97e52aec64c3dfceeb5c312d5`에서 준비하며 zip SHA-256·버전을 assets.json에 기록한다. 기본 NLP 경로는 `/app/.cache/text-analysis-nlp`이고 TEXT_ANALYSIS_NLP_DIR로 설정한다. 준비 스크립트 외에는 다운로드하지 않는다. spaCy 또는 WordNet 누락 시 KEYWORD_ASSETS_INVALID/KEYWORD_RESOURCES_UNAVAILABLE 등으로 준비를 실패시키고 구 구현으로 조용히 돌아가지 않는다.

두 자원은 번역 런타임의 전용 스레드에서 한 번 로딩하고 반복 사용한다. WordNet은 NLTK의 표준 로컬 corpus loader를 사용하며 이미 다른 경로의 corpus가 로딩됐다면 KEYWORD_CORPUS_CONFLICT로 거절한다. 다른 자원 경로로 바꿀 때는 프로세스를 재시작한다. lookup 캐시는 extractor당 최대4096개다.

keyword_rule_version은 `spacy-wordnet-keywords-v2`다. spaCy/NLTK/모델 버전, spaCy 데이터 해시, WordNet commit·zip 해시, 정책·구현 해시를 fingerprint에 포함한다. 기존 DB 컬럼(text[]/JSONB)은 그대로 사용하므로 마이그레이션은 없다. v1 결과를 v2 키워드로 비교하지 않고 새 프로필에서 재분석해야 한다. 프로필 DB 등록·활성화는 이번에 수행하지 않는다.

## 검증

실제 자원으로 미등록 단어·단복수·명사구, sofa/couch의 synset 일치, dog/cat·sofa/chair의 상위어 오탐 방지, 단일 의미 선택, 부정 동의어 제거, 분사/식별자 보존, 외국어 fallback과 프로필 혼용 거부를 확인한다. 합성 평가 데이터의 기대 키워드도 v2 형식으로 갱신했다. v1 수동 분류 사전의 재현율과 직접 비교하지 않는다.

운영 DB 후보 반영·실사용 정밀도/재현율·다의어 의미 판별·동시 부하·이미지 재빌드는 미검증이며 후속 범위다. WordNet은 문맥을 완전히 이해하는 의미 매칭 모델이 아니다.

### 2026-11-08 검증 결과

기존 backend 컨테이너 /app, 별도 kaifind_test_translation_20261108 DB와 기존 storage의 테스트 버킷에서 실제 번역·NLP 모델을 활성화한 전체405개 테스트가 통과했다(skip 없음). pip check는 의존성 충돌 없음, git diff --check도 통과했다. 실행 중 backend의 루트200 응답을 확인했다. DB 스키마·개발 데이터·4단계 API 파일은 변경하지 않았다.

합성19사례에서 정상18사례는 각3회 동일했고 반복문 스트레스1사례는 예상된 출력 한도로 거절됐다. 예상치 못한 실행 실패0건, 갱신된 v2 기대 키워드 재현율97.5%였다(번역의 leather 누락). 로딩·워밍업 약5.28초, 번역 경로 p50 약0.163초·p95 약1.748초, 로딩 후 RSS 약777MiB·평가 후 약779MiB였다. 이는 단일 합성 평가이며 매칭 서비스 전체의 정확도나 운영 지연 보장이 아니다. 실제 산출물은 .cache/text-analysis-evaluation.json 및 같은 이름의 -profile.json이다.

참고: [spaCy 형태·표제어 분석](https://spacy.io/usage/linguistic-features), [NLTK WordNet의 품사·synset](https://www.nltk.org/howto/wordnet.html).
