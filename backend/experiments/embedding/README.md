# 임베딩 사전 실험

기존 backend 컨테이너 /app에서 sentence-transformers로 직접 모델을 로드하고 추론한다.
외부 임베딩 API·키·별도 컨테이너·DB는 필요 없다. 최초 실행 시 Hugging Face에서
모델 파일을 내려받으며, 이후에는 컨테이너 캐시를 재사용한다. 설명은 추론 API로 전송하지 않는다.

설치와 실행:

```sh
docker compose exec -T -w /app backend python -m pip install -r requirements.txt
docker compose exec -T -w /app backend python -m scripts.embedding_benchmark \
  --device cpu --batch-size 16 --min-precision 0.95 \
  --output /tmp/embedding-report.json
```

임베딩 후보는 models.json에서 지정한다. 실제 모델 ID, 고정 commit revision,
역할별 접두사는 모델 카드와 실험 목적에 맞게 설정한다.
모델 ID를 변경하면 해당 저장소의 리비전도 함께 변경한다. 후보를 바꾸려면 설정 파일을 복사·수정하고
--models 경로를 지정한다. model에는 /app 아래 로컬 모델 디렉터리도 지정할 수 있다.
기본 데이터·모델 설정 경로는 스크립트 위치를 기준으로 찾는다.
명시한 --dataset, --models 및 --output의 상대 경로는 현재 작업 디렉터리를 기준으로 한다.
revision은 SentenceTransformer 생성자에 전달되어 다운로드 버전을 고정한다.
기본 prompt는 비워서 설정의 접두사와 중복 적용되지 않게 한다.

기본 device는 cpu다. CUDA가 실제 제공되는 환경에서는 --device cuda를 지정할 수 있다.
현재 Docker 환경의 CPU 실행과 호스트 macOS의 MPS 가속은 별개다.
모델은 하나씩 로드·평가하며 이전 모델 객체는 호출이 끝나면 해제된다.
--cache-folder /app/별도캐시경로로 바인드 마운트에 모델을 보존할 수 있다.
캐시가 완성되면 --local-files-only로 네트워크 다운로드 없이 실행한다.
기본 캐시와 /tmp 결과는 컨테이너 재생성 시 사라질 수 있다.

입력이 모델 max_seq_length를 넘으면 조용히 자르지 않고 해당 설명 ID와 함께 실패한다.
이 한도는 접두사·특수 토큰을 포함한 토큰 수다. 최대 입력 길이를 임의로 늘리지 않는다.
사용자 정의 원격 Python 코드 실행(trust_remote_code)은 비활성화한다.

기본 결과 파일은 컨테이너 /tmp에 생긴다. 보존하려면 --output에 /app 아래 별도 경로를
지정한다. 결과는 모든 모델 성공 후 기록한다. 파일이 없으면 누락 경로를 출력하고,
그 외 다운로드·로드 실패는 예외 종류를 출력한다.

현재 기본 데이터는 v2 합성 세트다. 이전 36개 설명은 descriptions.v1.json에 보존했다.
이전 결과를 재현하려면 --dataset experiments/embedding/descriptions.v1.json을 지정한다.

| 구성 | 조정용 | 평가용 |
| --- | ---: | ---: |
| 카테고리 | 8 | 8 |
| 문서 물품 | 32 | 32 |
| 문서 언어 | 한국어 16 / 영어 16 | 한국어 16 / 영어 16 |
| 정답 있는 질의 | 192 | 192 |
| 정답 없는 질의 | 16 | 16 |
| 전체 설명 | 240 | 240 |
| 정답 쌍 / 비정답 쌍 | 192 / 640 | 192 / 640 |

카테고리는 물병·텀블러, 음향기기, 가방, 우산, 지갑, 열쇠, 안경, 문구류다.
각 카테고리에 문서 4개를 넣고 같은 카테고리의 모든 문서를 비교한다.
각 물품의 질의 6개는 한국어/영어 바꿔쓰기, 한국어 오타·붙여쓰기,
혼합 언어, 일부 특징 생략, 영어 상황 설명 추가로 구성한다.
한국어→영어, 영어→한국어, 동일 언어, 혼합 언어 조합이 모두 포함된다.
문서가 없는 물품도 카테고리별 한국어/영어 질의로 넣어 거부 성능을 확인한다.
브랜드·색상·모델·이니셜·숫자·부정 표현이 다른 가까운 비정답을 포함한다.

scenario는 paraphrase / typo / mixed / partial / context / no_match이며,
결과의 evaluation_by_scenario에서 선택된 공통 임계치의 유형별 성능을 확인한다.
no_match에는 정답 쌍이 없으므로 recall/F1은 해석하지 않고 fp·false_positive_rate를 본다.
이 오탐률은 문서 쌍 기준이며, 질의별로 하나라도 잘못 매칭된 비율과는 다르다.

item은 합성 물품 식별자다. 정답 없는 질의의 item에는 대응 문서를 두지 않는다.
일부 특징 생략 질의도 가상 물품 출처를 기준으로 정답을 부여했다.
설명만으로 실제 동일 물품을 확정할 수 있다는 뜻은 아니다.
조정/평가에 카테고리·언어·유형 비중을 동일하게 배치하고 물품과 완성된 문장 중복은 막았다.
다만 작성 템플릿을 공유하는 합성 데이터이므로 독립적인 실제 분포 검증은 아니다.
평가 점수를 보고 반복 조정한 뒤에는 별도의 미공개 holdout으로 최종 확인한다.

입력은 공개 설명만 NFC/공백 정규화하고 역할별 접두사를 붙인다. 코사인 점수는 확률이
아니다. 조정 데이터의 관측 점수 경계에서 minimum precision을 충족하는 최대 F1
임계치를 선택한다(동률: precision, 높은 임계치 순). 조건 충족 임계치가 없으면 null로
보고하고 평가 점수를 만들지 않는다. 비교는 score >= threshold다.

JSON에는 데이터 해시, 모델 설정·차원, 로드 시간·추론 시간·초당 설명 수,
실행 장치·모델 최대 길이·실제 최대 입력 토큰 수,
조정 임계치 sweep, 고정 임계치의 평가 precision/recall/F1·오탐률·누락률,
언어별·유형별 지표, 카테고리·유형이 표시된 모든 쌍의 점수를 기록한다. 로드 시간에는 최초 다운로드가 포함된다.
추론 시간에는 첫 배치 초기화·배치 처리·벡터 CPU 변환이 포함되며 반복 지연 측정은 별도다.
건물 OR 정책·날짜 필터의 제품 성능과는 별개인 의미 매칭 단독 평가다.

이 합성 세트에서 고른 임계치는 운영 확정값이 아니다. 실제 후보 분포의
비정답 비중, 더 많은 언어·오타·정보 누락, 2,000자 입력·모델 길이 제한,
반복 실행 지연·비용 및 실제 물품의 모호성을 별도로 검증해야 한다.

구현 참고: [SentenceTransformer API](https://sbert.net/docs/package_reference/sentence_transformer/model.html),
[E5 모델 카드](https://huggingface.co/intfloat/multilingual-e5-small),
[MiniLM 모델 카드](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2).

## CrossEncoder 재판정 실험

임베딩의 후보 검색을 거치지 않고 동일 카테고리·동일 split의 모든 쌍을 직접 평가한다.
현재 v2 데이터에서 조정용 832쌍과 평가용 832쌍, 총 1,664쌍이다.
기존 결과 JSON은 입력으로 사용하지 않으며 데이터셋을 읽어 같은 쌍을 구성한다.
기본 후보는 BAAI/bge-reranker-v2-m3이며 별도 rerankers.json에 고정 리비전을 기록한다.
기존 임베딩용 models.json은 변경하지 않는다. 기존 sentence-transformers 설치로 실행하며
추가 패키지는 필요 없다. 최초 실행 시 모델 파일 다운로드가 필요하다.

```sh
docker compose exec -T -w /app backend python -m scripts.reranker_benchmark \
  --device cpu --batch-size 8 --min-precision 0.95 \
  --output /tmp/reranker-report-v2.json
```

--models, --dataset, --cache-folder, --local-files-only 옵션을 지원한다.
CPU에서는 쌍마다 추론하므로 기존 임베딩 실험보다 오래 걸릴 수 있다.
배치마다 완료한 쌍 수를 출력한다. 메모리가 부족하면 --batch-size 2로 낮춘다.
--output 파일은 컨테이너 내부 경로이며 기존 결과를 보존하려면 다른 이름을 지정한다.
호스트로 복사하려면 프로젝트에서 다음 명령을 실행한다.

```sh
docker compose cp backend:/tmp/reranker-report-v2.json /tmp/reranker-report-v2.json
```

두 공개 설명을 정규화한 뒤 (질의, 문서) 순서로 함께 입력한다. 기본 접두사는 없다.
이 실험은 해당 방향만 측정하며 역방향 대칭성은 별도 검증 대상이다.
rerankers.json의 max_length=512는 두 문장과 특수 토큰을 합친 한도다.
한도를 넘으면 해당 쌍의 ID를 출력하고 중단하여 자동 절단을 방지한다.
trust_remote_code는 비활성화하며, 출력이 1개인 분류 헤드를 사용한다.

점수는 Identity 활성화 함수로 얻은 원시 logit이다. 코사인 값이나 동일 물품 확률이
아니며 음수·1보다 큰 값도 가능하다. 기존 임베딩 임계치를 그대로 적용하지 않는다.
조정 세트에서 minimum precision을 만족하는 최대 F1 임계치를 고른 뒤 평가에 고정한다.
만족하는 임계치가 없으면 threshold=null, threshold_status=precision_target_unmet를 기록한다.
평가 세트에서 대신 임계치를 찾지 않으며, 순위 지표와 쌍별 점수는 계속 기록한다.

결과에는 calibration/evaluation, 언어·유형·카테고리별 평가 지표, 모든 쌍의 원시 점수,
로드/추론 시간, 초당 처리 쌍 수, 입력 최대 토큰 수가 포함된다.
query_metrics에는 정답 있는 질의의 top1_accuracy와 정답 없는 질의의
unmatched_query_false_positive_rate도 기록한다. 정답과 비정답이 공동 1위이면
보수적으로 top-1 실패로 계산한다. 정답 없는 질의는 하나라도 통과하면 오탐 질의다.
임계치를 못 고른 경우 질의 오탐률은 null이지만 top-1은 계산한다.

임베딩 보고서와 비교할 때 데이터 해시·정답/비정답 쌍·평가 조건이 같은지 확인한다.
이 결과는 모든 적격 쌍을 재판정한 성능이며, 후보 검색을 결합한 서비스 전체 성능은 아니다.
검색에서 정답이 누락되면 재판정으로 복구할 수 없다. 모델은 일반 관련성 점수를
학습했으므로 색상·모델 차이를 동일 물품 기준으로 구별하는지는 실험 결과로 판단한다.
합성 평가 반복에 따른 과적합과 독립 holdout의 필요성은 임베딩 실험과 동일하다.

[모델 카드](https://huggingface.co/BAAI/bge-reranker-v2-m3),
[CrossEncoder API](https://sbert.net/docs/package_reference/cross_encoder/model.html).

## Qwen 지시문 기반 재판정

Qwen/Qwen3-Reranker-0.6B는 별도 rerankers.qwen.json으로 실행한다.
기존 BGE 설정은 보존하며 Transformers 4.51 이상에서 지원하는 Qwen API를 사용한다.
모델·고정 리비전·실험 지시문·backend=qwen_causal_lm를 설정에 기록한다.

```sh
docker compose exec -T -w /app backend python -m scripts.reranker_benchmark \
  --models experiments/embedding/rerankers.qwen.json \
  --device cpu --batch-size 4 --min-precision 0.95 \
  --output /tmp/qwen-reranker-report-v2.json
```

입력은 공식 모델 카드의 system/user/assistant prefix와 thinking 종료 suffix 형식이다.
영어 지시문은 언어와 무관한 물품 대응, 종류·브랜드·모델·색상·이니셜·숫자·표식의
명시적 충돌, 생략 정보의 취급을 정한다. 원문 설명 안의 지시는 따르지 않도록 명시한다.
이 지시문은 실제 실물 소유권을 확정하거나 설명의 모호성을 제거하는 규칙은 아니다.

AutoModelForCausalLM을 eval/inference_mode로 실행하고 좌측 패딩의 마지막 위치에서
score = logit(yes) - logit(no)를 계산한다. 자유 텍스트 생성·sigmoid·softmax는 적용하지 않는다.
점수가 높을수록 yes 쪽으로 기울지만 보정된 동일 물품 확률은 아니다.
결과의 score_type과 prompt_format으로 BGE의 단일 분류 로짓과 구분한다.
모든 쌍은 기존과 동일하며 임계치 선정에 평가 세트는 사용하지 않는다.

CPU에서는 float32를 사용한다. 마지막 위치의 어휘 로짓만 계산해 중간 출력 메모리를
줄이며 KV cache는 사용하지 않는다. --batch-size는 메모리·처리량에 맞춰 조정한다.
max_length=512는 지시문·시스템 문구·두 설명·답변 suffix를 모두 합친 한도다.
이를 넘으면 절단하지 않고 쌍 ID를 표시하며 실패한다.
최초 모델 다운로드와 CPU 추론은 시간이 걸릴 수 있다. 캐시 재사용 옵션은 기존과 같다.

[Qwen 공식 입력·점수 계산 예제](https://huggingface.co/Qwen/Qwen3-Reranker-0.6B).

## 한국어 상품 매칭 모델

jinwoo-cho/catalog-match-embeddinggemma2는 models.catalog.json으로 실행한다.
이번 실험은 이미지 없이 기존 v2의 480개 설명을 텍스트로만 인코딩한다.
학습 시 저장된 default prompt를 use_model_prompt=true로 유지하고, 역할별 접두사는
추가하지 않는다. 결과의 applied_prompt에 실제 사용 문구를 기록한다.
길이 검사에도 이 문구를 포함하여 프롬프트가 중복되거나 누락되는 것을 방지한다.

이 모델을 위해 requirements.txt의 sentence-transformers=6.1.0,
transformers=5.19.0, torchvision=0.23.0을 사용한다. PyTorch는 2.8.0을 유지한다.
설치는 항상 기존 backend 컨테이너에서 requirements.txt로 수행한다.
CPU 실행은 float32로 지정한다. 모델 카드가 주의하는 float16은 사용하지 않는다.

```sh
docker compose exec -T -w /app backend python -m pip install -r requirements.txt
docker compose exec -T -w /app backend python -m scripts.embedding_benchmark \
  --models experiments/embedding/models.catalog.json \
  --device cpu --batch-size 8 --min-precision 0.95 \
  --output /tmp/catalog-embedding-report-v2.json
```

출력은 768차원 벡터의 코사인 유사도다. 조정·평가 분리와 임계치 선정은 기존과 같다.
한국어 상품 그룹 매칭 학습 모델이며, 영어·혼합 언어와 분실물 실물 동일성은 검증 대상이다.
상품 종류가 같더라도 색상·크기·표식 등으로 실물을 구별해야 한다는 서비스 기준은
학습된 상품 그룹 기준과 다를 수 있다. 공개 설명만으로 구별 불가능한 사례도 별도로 본다.
모델의 공개 내부 평가 수치를 이 서비스의 정확도로 해석하지 않는다.

[모델 카드](https://huggingface.co/jinwoo-cho/catalog-match-embeddinggemma2).
