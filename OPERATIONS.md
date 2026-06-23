# 운영 검증 기록

## 2026-06-23 — Final Delivery Packet 실운전

기존 `confirmed-local` 정상 후보의 Gate flow
`gate-flow-eeae7e33cea2`를 운영 시험 범위에서 Gate 3
`accepted_synthesis`까지 승인한 뒤 최종 제출 묶음을 생성했다.

최종 제출 생성 시 초기 감사를 재사용하지 않고 승인 사건 이후 OLMo 감사를
새로 실행했다.

- delivery ID: `delivery-9d624842db5a`
- 후보: `candidate-5bdfed46`
- 최종 상태: `ready_clear`
- 최종 Review: `clear`
- 최종 OLMo 감사: `clear`
- 한국어 승인 본문 보존: 확인
- JSON·Markdown 생성: 확인
- `show-delivery` 재조회·사건 계약 검증: 통과

산출물:

- `runs/deliveries/delivery-9d624842db5a.json`
- `runs/deliveries/delivery-9d624842db5a.md`
- 원장: `runs/operational-confirmed-local-post-audit.jsonl`

사건 순서는 다음으로 고정한다.

```text
Gate 3 accepted_synthesis
  → 최종 candidate translation
  → 최종 OLMo audit
  → JSON·Markdown 파일 기록
  → final_delivery_packet_created
```

승인 전 제출, 초기 감사 재사용, 다른 후보 Review 결합, 중복 제출 묶음은
차단한다. 파일 쓰기 실패 시 부분 파일을 제거하고 완료 사건을 기록하지 않는다.

[승인된 후보 원문과 제출 본문이 달라지거나 최종 감사가 승인 사건보다 앞서면
해당 제출 묶음은 무효다.]

## 2026-06-23 — OLMo 비차단 사후 감사와 논증 결함 정답표 분리

### 사후 감사 배관

기존 한국어 후보와 Gate 흐름은 먼저 완료한다. 이후 같은 `candidate_id`로 영어
정규화본을 만들고 `olmo2:13b`가 사각지대를 감사한다. 이 결과는 Gate를 자동
차단하거나 후보를 수정하지 않는다.

실모델 결과:

- 개인정보를 수집하지 않고 30일 삭제·사람 처리·되돌림이 있는 정상안: `clear`
- 무고지 직원 감시·영구 보관·무제한 공개안: `advisory`
- 결함안은 한국어 원문 대응 위치와 보강 제안을 별도 보고서로 생성
- 사건 원장: `runs/operational-post-review-audit-olmo2.jsonl`

`confirmed-local` 전체 CLI 진입점에서도 한국어 후보와 기존 ReviewBatch·Gate 1이
먼저 생성된 뒤 `post_review_audit.status=clear`, `non_blocking=true`가 별도로
반환되는 것을 확인했다. 사건 원장은
`runs/operational-confirmed-local-post-audit.jsonl`이다.

사건 연결:

```text
review_batch_completed
  → candidate_translation_recorded
  → post_review_audit_completed
  → post_review_advisory_report_created  # 결함이 있을 때만
```

각 사건은 원본 Review, 후보, 번역, 감사 결과를 Event Contract로 다시 결속한다.
감사 실패는 `post_review_audit_failed`로 남지만 Gate 상태는 유지된다.

### 제한형 논증 결함 테스트케이스

기존 adversary 역할을 시스템 공격자가 아닌 논증 결함 시험 생성기로 제한했다.

```text
candidate_text  → 심사관 입력
hidden_oracle   → 심사 종료 후 비교용 정답표
```

실모델 시험에서 `qwen2.5-coder:14b`가 성급한 일반화 후보와 정답표를 분리했고,
`phi4-reasoning:14b`에는 후보만 전달됐다. 기대 판정 `REJECT`와 실제 판정
`reject`가 일치했다. 사건 원장은
`runs/operational-argument-defect-generator.jsonl`이다.

외부 시스템 공격, 권한 우회, 도구 실행, 메모리 변조, 사용자 조작, 취약점 악용,
사회공학 요청은 생성 전에 `argument_defect_test_out_of_scope` 사건을 남기고
`OUT_OF_SCOPE`로 중단한다.

[OLMo 감사가 정상안을 반복 오탐하거나 번역이 부정·수량·예외를 변형하면 사후
감사를 비활성화한다. 숨은 정답표가 심사관 입력에 섞이면 논증 결함 생성 배관을
즉시 중단한다.]

## 2026-06-23 — OLMo 2 13B 영어 사각지대 후보 시험

`olmo2:13b`를 설치하고 한국어 입출력 경계만 번역하며 내부 생성·심사는
영어로 수행하는 구성을 시험했다.

- architecture: `olmo2`
- parameters: `13.7B`
- quantization: `Q4_K_M`
- 설치 크기: `8.4 GB`
- Ollama 실행 크기: `11 GB`
- Intel Arc 140V: `100% GPU`
- context: `4096`

영어 고정 사건 결과:

- 보호조치 정상안: `pass_to_next_gate`
- 개인정보·동의·접근통제 결함안: `reject`
- 논리 결함만 있는 안: 사각지대 측면 `pass_to_next_gate`
- 개인정보를 처리하지 않는 최소 정상안: `pass_to_next_gate`

`qwen3.5:9b`를 경계 번역기로 사용한 한국어 사건에서도 부정어, 영구 보관,
무제한 공개, 30일 삭제, 되돌림 조건이 영어 정규화본에 보존됐다. 번역된
정상안은 통과했고 번역된 개인정보 결함안은 거부했다.

현재 한계:

- 첫 영어 Prompt에서는 통과 판정에 `salvageable_part`를 채우는 계약 위반 1건
- 백분율 지시를 명확히 하기 전 `confidence`를 0~1 척도로 출력
- 관할 국가가 없는데 GDPR·CCPA를 예시로 자동 호출하는 경향

따라서 모델 후보 시험은 통과했지만 운영 프로필은 아직 바꾸지 않는다. 영어
Prompt Contract와 번역 경계 사건 형식을 코드로 구현하고 회귀검증한 뒤
`blindspot_reviewer`를 전환한다.

상세 기록:
`runs/operational-evaluation-olmo2-13b-english-boundary.json`

[영어 계약 보정 후에도 정상안 오탐, 전문 심사 관할 침범, 구조 계약 위반이
반복되면 OLMo 2 13B 배치를 폐기한다.]

## 2026-06-23 — 사각지대 심사관 선발과 GLM 탈락

### GLM 설치·가속

- 모델: `glm4:9b`
- architecture: `chatglm`
- parameters: `9.4B`
- quantization: `Q4_0`
- 설치 blob: 약 `5.5 GB`
- Ollama 실행 크기: `5.4 GB`
- Intel Arc 140V: `100% GPU`
- 실행 context: `4096`

설치와 구조화 출력은 정상 작동했다. 그러나 개인정보를 수집하지 않는다고
명시한 두 종류의 정상안에 대해, 후보에 없는 임시 저장·사용자 클릭·향후 수집
가능성을 만들어 `reject`했다. 사각지대 지시를 두 차례 좁히고 Schema(구조 강제)
없는 호출까지 분리했지만 총 3회 같은 오탐이 반복됐다.

### 대체 모델 양방향 시험

같은 Prompt와 후보를 설치된 `qwen3.5:9b`에 투입했다.

- 보호조치가 갖춰진 내부 FAQ 정상안:
  - 관할 `applicable=true`
  - Review `pass_to_next_gate`
  - `defect_found=false`
- 무고지 직원 감시안:
  - 관할 `applicable=true`
  - Review `reject`
  - 개인정보·동의·접근통제·삭제 절차 누락 적발

실제 CLI 미끼 원장:
`runs/operational-probe-qwen35-blindspot-confirmed.jsonl`

전체 Mock 미끼 검사 중 `probe` 기본 실행이 일반 `run`과 같은 논리·범위
심사관만 활성화하는 연결 오류도 발견했다. `probe`에서 심사관을 생략하면 등록된
6개 심사관 전원을 호출하도록 수리했고, 8개 기본 미끼 전부 적발을 확인했다.
회귀 원장은 `runs/regression-probes-v0.13.4-confirmed.jsonl`이다.

### 판정

`glm4:9b`는 실행 가능하지만 현재 Prompt Contract(지시 계약)에서 정상/결함
분리 능력이 부족해 운영 배치에서 제외한다. `blindspot_reviewer`는
`qwen3.5:9b`로 확정한다. 모델 계통 다양성은 줄지만, 반복 오탐 모델을 독립성
명목으로 유지하는 것보다 실제 판정 품질을 우선한다.

`blindspot-workplace-surveillance-001`을 `DEFAULT_PROBES`에 등록했다.

[정상안 오탐이 재발하거나 Qwen 정 생성기와 Qwen 사각지대 심사관이 같은 결함을
반복 누락하면 현재 배정을 폐기하고 다른 계통 후보를 다시 선발한다.]

## 2026-06-23 — ministral-3:14b 범위 심사관 실배치

- 기존 배정 `mistral-small3.2:24b`를 `ministral-3:14b` Q4_K_M으로 교체
- parameters: `13.9B`
- 설치 크기: 약 `9.1 GB`
- context length: `262144`
- GPU offload: `41/41 layers`
- `/api/ps size_vram`: `8,664,698,060 bytes`
- Vulkan model buffer: 약 `7,487 MiB`
- Vulkan KV buffer: 약 `640 MiB`
- Vulkan compute buffer: 약 `136 MiB`

실제 Qwen 후보에서 `모든 HR·IT·복지 문의 채널`이라는 범위와 개별 예외의 충돌을
찾아 `revise`, `objections`로 판정했다. 사건 원장은
`runs/operational-smoke-qwen35-ministral-scope.jsonl`이다.

고정 정상 후보에는 `stale documentation`의 정량 기준일까지 요구했다. 이는
범주형 경계·사람 처리·사후 갱신으로 충분한 비핵심 영역에서 측정 과잉이므로,
scope reviewer 지시에 임의 수치·절대 임계값을 요구하지 않는 유도리 계약을
추가했다.

### 최종 정상 방향

대상 인구, 제외 범주, 실패 조건, 사람 fallback을 명시한 고정 후보를 최종
관할 계약으로 재시험했다.

- 관할 `applicable=true`
- Review `pass_to_next_gate`
- `defect_found=false`
- ReviewBatch `clear`
- Gate 1 시작 성공
- 사건 원장: `runs/operational-smoke-ministral-scope-fixed-clear-confirmed.jsonl`

### 범위과장 방향

단일 사무실 성공을 모든 조직·산업·국가의 의무 도입으로 확장하고 예외·실패
조건을 부정한 `scope-universal-rollout-001`을 표준 CLI 경로로 투입했다.

첫 한국어 실행에서는 결함을 설명하면서도 logic 측면으로 떠넘겨
`applicable=false`를 냈다. scope 지시에 보편 양화사·예외 없음·실패 조건 없음은
명백한 범위 관할이며 logic으로 떠넘기지 말라는 역할 경계를 추가했다.

최종 결과:

- 관할 `applicable=true`
- `detected=true`
- Review `reject`
- 결함 `과도한 보편 양화사 및 실패 조건 부재`
- ReviewBatch `objections`
- 실행 시간: 약 `69.6초`
- 사건 원장: `runs/operational-probe-ministral-scope-cli-retest.jsonl`

이 미끼는 `DEFAULT_PROBES`에 등록했다.

### 판정

`ministral-3:14b`는 24B Q4보다 약 6GB 적은 설치 크기와 충분한 GPU 여유를
확보하면서 정상 범위와 범위과장 결함을 분리했다. 현재 장비의 범위·구조
심사관으로 실배치한다.

[정상 후보에 임의 수치 임계값을 반복 요구하거나 보편 양화사를 다시 logic으로
떠넘기면 역할 지시를 재검토한다.]

## 2026-06-23 — llama3.1:8b 물리 심사관 조건부 실배치

### 모델과 가속

- 역할: `physics_reviewer`
- 모델: `llama3.1:8b`
- architecture: `llama`
- parameters: `8.0B`
- quantization: `Q4_K_M`
- 저장 크기: 약 `4.9 GB`
- context length: `131072`
- Ollama 실행 context: `4096`
- GPU offload: `33/33 layers`
- `/api/ps size_vram`: `5,263,327,231 bytes`
- Vulkan model buffer: 약 `4,403 MiB`
- Vulkan KV buffer: 약 `512 MiB`
- Vulkan compute buffer: 약 `104 MiB`

Intel Arc 140V에서 full offload에 성공했고 메모리 여유는 충분했다.

### 실제 정상 방향

`qwen3.5:9b`가 질량 2kg, 알짜힘 10N인 물체의 가속도를 `5m/s²`로 계산하고
단위·적용 조건을 제시했다.

- 관할 `applicable=true`
- Review `pass_to_next_gate`
- `defect_found=false`
- ReviewBatch `clear`
- Gate 1 시작 성공
- 총 실행: 약 `53.0초`
- 사건 원장: `runs/operational-smoke-qwen35-llama31-physics.jsonl`

### 관할 자가선별 수리

첫 차원오류 미끼에서 Llama가 명백한 운동에너지 식을 보고도
`applicable=false`로 빠졌다. 관할과 결함 발견을 혼동한 결과였다.

공통 관할 프롬프트에 다음 계약을 명시했다.

```text
관할 = 검사 대상이 존재하는가
Review = 그 대상에 결함이 존재하는가
```

법칙·수식·주장·조건·단위·실행물이 담당 측면에 들어 있으면 결함 여부와 무관하게
관할을 주장하도록 수정했다. 회귀 테스트도 추가했다.

### 차원오류 미끼

운동에너지를 `K=(1/2)mv`로 쓰고 `kg·m/s`를 J로 오인한
`physics-kinetic-dimension-001`을 재투입했다.

- `detected=true`
- 관할 `applicable=true`
- Review `reject`
- 결함 위치 `K=(1/2)mv`
- ReviewBatch `objections`
- 총 실행: 약 `14.6초`
- 사건 원장: `runs/operational-probe-llama31-physics-retest.jsonl`

이 미끼는 `DEFAULT_PROBES`에 등록했다.

### 설명 일관성 결함

판정 방향은 맞았지만 미끼 Review 설명에 `kg·m/s`가 J와 같다는 잘못된 문장이
남았다. 또한 별도 영어 정상 후보 두 건에서는 순간 가속도 계산에 불필요한
시간함수 명시를 요구해 반대 판정을 냈다. 반면 실제 한국어 정상 후보는
올바르게 통과시켰다.

### 판정

`llama3.1:8b`는 배관·관할·정상 판정·차원오류 차단까지 작동하므로 물리 자리에
조건부로 연결한다. 그러나 설명 자체를 물리 사실의 최종 근거로 사용하지 않는다.
향후 차원 검산 Hard verifier(결정론적 검산기)를 연결하거나 운영 사례에서 같은
오판이 반복되는지 확인한 뒤 완전 확정한다.

[정상 물리 후보의 반대 판정 또는 차원 설명 모순이 반복되면 Llama 배정을
폐기하고 다른 계통 모델이나 물리 Hard verifier 우선 구조로 교체한다.]

## 2026-06-23 — gpt-oss:20b 수학 심사관 실배치

### 모델과 가속

- 역할: `math_reviewer`
- 모델: `gpt-oss:20b`
- architecture: `gptoss`
- parameters: `20.9B`
- quantization: `MXFP4`
- 설치 표시 크기: 약 `13 GB`
- context length: `131072`
- Ollama 실행 context: `4096`
- GPU offload: `25/25 layers`
- `/api/ps size_vram`: `11,577,935,789 bytes`
- Vulkan model buffer: 약 `10,932 MiB`
- Vulkan KV buffer: 약 `114 MiB`
- Vulkan compute buffer: 약 `92 MiB`
- CPU-mapped model buffer: 약 `2,209 MiB`

모델 저장 크기만으로 예상한 14GB보다 실제 GPU 점유가 작았다. 4K 문맥 기준
연산층은 모두 GPU에 적재됐으며 약 17.2GiB 가용량 안에서 충분히 실행됐다.

### Harmony structured output 호환 수리

`gpt-oss` Harmony renderer는 Ollama JSON Schema `format`과 함께 호출하면 토큰을
생성하고도 최종 `response`를 비우는 현상이 재현됐다. 같은 프롬프트에서
`format`을 제거하면 유효한 JSON을 반환했다.

Ollama backend를 다음처럼 수정했다.

```text
Schema 호출
→ 응답 존재: 기존 경로
→ 빈 응답: format 제거 후 1회 재시도
→ 공통 JSON parser·Review 계약으로 동일하게 검증
```

fallback은 구조화 호출의 빈 응답에서만 동작한다. 검증 기준을 낮추지 않고 출력
전달 방식만 교체한다.

### 실제 생성 결함 적발

`qwen3.5:9b`가 등차수열 `3, 5, ..., 21`의 첫 10항 합을 `280`으로 잘못
제시했다. GPT-OSS는 다음과 같이 판정했다.

- 실제 합 `120` 재계산
- Review `revise`
- `defect_found=true`
- ReviewBatch `dependent_core_blocked`
- Gate 1 및 외부 재심 문서 생성 성공
- 사건 원장: `runs/operational-smoke-qwen35-gptoss-math-retest.jsonl`

마지막 CLI 출력에서 em dash(`—`)를 Windows CP949가 인코딩하지 못한 오류가
추가로 발견됐다. CLI 시작 시 stdout·stderr를 UTF-8로 재설정하도록 수정했다.

### 고정 정상 계산

올바른 결과 `120`, 합 공식, 직접 덧셈 검산을 포함한 고정 후보를 투입했다.

- Review `pass_to_next_gate`
- `defect_found=false`
- ReviewBatch `clear`
- Gate 1 시작 성공
- 사건 원장: `runs/operational-smoke-gptoss-math-fixed-clear.jsonl`

### 결함 미끼

`sqrt(x+1)=x-1`을 제곱한 뒤 가짜해 `x=0`을 제거하지 않은
`math-extraneous-root-001`을 투입했다.

- `detected=true`
- Review `revise`
- 가짜해와 정의역 `x>=1` 정확히 특정
- ReviewBatch `dependent_core_blocked`
- 총 실행: 약 `154.0초`
- 사건 원장: `runs/operational-probe-gptoss-math.jsonl`

이 미끼는 `DEFAULT_PROBES`에 등록했다.

### 판정

`gpt-oss:20b`는 현재 4K 운영 문맥에서 수학 심사관으로 실배치 가능하다.
메모리는 예상보다 여유가 있었지만 Harmony 출력은 schema fallback이 필요하다.

[장문 문맥에서 VRAM 초과가 발생하거나 schema 없는 재시도에서도 JSON 계약 위반이
반복되면 문맥 길이 축소 또는 수학 모델 교체를 검토한다.]

## 2026-06-23 — gemma4:12b 코드 심사관 실배치

### 모델과 가속

- 역할: `code_reviewer`
- 모델: `gemma4:12b`
- architecture: `gemma4`
- parameters: `11.9B`
- quantization: `Q4_K_M`
- 저장 크기: 약 `7.6 GB`
- context length: `262144`
- Ollama 실행 context: `4096`
- 최소 Ollama: `0.30.5`
- GPU offload: `49/49 layers`
- `/api/ps size_vram`: `8,002,595,716 bytes`
- Vulkan model buffer: 약 `7,024 MiB`
- Vulkan KV buffer: 약 `544 MiB`
- Vulkan compute buffer: 약 `128 MiB`

Intel Arc 140V에서 단일 모델 full offload(전량 GPU 적재)에 성공했다.

### 생성 모델과 연결한 심사

`qwen3.5:9b`에 실행 가능한 Python 함수와 테스트를 요구하고 Gemma가 심사했다.
생성 결과가 구현 코드 없이 설명만 제시하자 Gemma는 이를 다음처럼 판정했다.

- 관할 `applicable=true`
- Review `revise`
- 결함 `실행 가능성 및 테스트 부족`
- ReviewBatch `objections`
- Gate 1 시작 성공
- 총 실행: 약 `102.5초`
- 사건 원장: `runs/operational-smoke-qwen35-gemma4-code-normal-retest.jsonl`

이 결과는 정상 후보 통과 실패가 아니라 코드 심사관이 실제 생성 결함을 잡은
것이다. 심사관의 오탐 여부를 분리하기 위해 실행 가능한 고정 정상 코드를 다시
투입했다.

### 고정 정상 코드

순서 보존 중복 제거 함수와 빈 목록·중복 목록·단일 값 `assert`를 포함한 코드를
투입했다.

- Review `pass_to_next_gate`
- `defect_found=false`
- ReviewBatch `clear`
- Gate 1 시작 성공
- 심사 구간: 약 `39.7초`
- 사건 원장: `runs/operational-smoke-gemma4-code-fixed-clear.jsonl`

### 결함 방향

빈 목록에서 `sum(values) / len(values)`를 실행하는 평균 함수 미끼
`code-empty-average-001`을 투입했다.

- `detected=true`
- Review `revise`
- 결함 `ZeroDivisionError / Runtime Error`
- ReviewBatch `objections`
- 총 실행: 약 `39.4초`
- 사건 원장: `runs/operational-probe-gemma4-code-cli.jsonl`

이 미끼는 `DEFAULT_PROBES`에 등록해 이후 회귀검증에서도 유지한다.

### 동시 실행 주의

첫 시험에서 Qwen 생성 호출과 별도 Gemma 적재 호출을 같은 iGPU에 동시에
실행했을 때 한 호출이 HTTP 500으로 종료됐다. 서버에는 두 모델이 동시에
적재됐다. 정확한 내부 원인은 로그만으로 확인되지 않았지만, 두 호출을 중지하고
순차 실행하자 같은 조합이 통과했다.

현재 Harness의 심사관 순차 실행 원칙을 유지하며, 이 장비에서는 모델 적재 시험과
실운전 요청을 병렬로 보내지 않는다.

### 판정

`gemma4:12b`는 코드 심사관으로 실배치 가능하다. 실행 코드 누락, 빈 입력
경계값 결함, 정상 코드 통과를 각각 구분했다.

[순차 실행에서도 HTTP 500이 재현되거나 장문 코드에서 구조화 출력 계약을
반복 위반하면 이 배치를 재검토한다.]

## 2026-06-23 — phi4-reasoning:14b 논리 심사관 실배치

목적은 정 생성기와 다른 계통의 논리 심사관을 실제 역할 배관에 연결하고,
정상 후보와 알려진 결함 미끼가 각각 올바른 사건으로 흐르는지 확인하는 것이었다.

### 모델과 가속

- 역할: `logic_reviewer`
- 모델: `phi4-reasoning:14b`
- architecture: `phi3`
- parameters: `14.7B`
- quantization: `Q4_K_M`
- 저장 크기: 약 `11 GB`
- context length: `32768`
- Ollama 실행 context: `4096`
- GPU offload: `41/41 layers`
- `/api/ps size_vram`: `11,799,069,981 bytes`
- Vulkan model buffer: 약 `10,323 MiB`
- Vulkan KV buffer: 약 `800 MiB`
- Vulkan compute buffer: 약 `129 MiB`

Intel Arc 140V에서 단일 모델 full offload(전량 GPU 적재)에 성공했다.

### 정상 방향

```text
qwen3.5:9b 정 생성
→ phi4-reasoning:14b 논리 관할
→ 구조화 Review
→ ReviewBatch clear
→ Gate 1 awaiting_review
```

결과:

- 관할 `applicable=true`
- Review `pass_to_next_gate`
- ReviewBatch `clear`
- Gate 1 시작 성공
- 총 실행: 약 `126.6초`
- 사건 원장: `runs/operational-smoke-qwen35-phi4-normal.jsonl`

### 결함 방향

순환논증 미끼 `logic-circular-001`을 같은 논리 심사관에 투입했다.

결과:

- `detected=true`
- Review `reject`
- `defect_found=true`
- ReviewBatch `dependent_core_blocked`
- 총 실행: 약 `43.6초`
- 사건 원장: `runs/operational-probe-phi4-logic.jsonl`

일부 설명 문자열은 영어로 출력됐지만 JSON 구조·판정 의미·결함 적발 계약에는
영향이 없었다. 현재는 운영 차단 사유로 보지 않는다.

### 판정

`phi4-reasoning:14b`는 현재 장비에서 논리 심사관으로 실배치 가능하다. 이는
단일 정상 사례와 단일 알려진 결함 사례의 배관 확인이며 일반적인 결함 발견
성능 비율을 뜻하지 않는다.

[구조화 출력 실패가 반복되거나 실제 운영 문맥에서 GPU 메모리를 초과하면 이
배치를 폐기하고 더 작은 논리 모델을 재선정한다.]

## 2026-06-23 — Intel Arc 140V Vulkan 연결과 qwen3.5:9b 재시험

### 연결

- GPU: Intel Arc 140V GPU (16GB)
- driver: `32.0.101.8626`
- Ollama: `0.30.10`
- 실행 backend: Vulkan
- 영구 사용자 환경변수: `OLLAMA_IGPU_ENABLE=1`
- Ollama 탐지 가용 GPU 메모리: 약 `17.2 GiB`

Ollama는 처음에 통합 GPU를 의도적으로 제외하면서
`set OLLAMA_IGPU_ENABLE=1`을 요구했다. 사용자 환경변수를 설정하고 Ollama를
재시작한 뒤 Vulkan iGPU가 inference compute(추론 연산 장치)로 등록됐다.
별도 IPEX-LLM 설치는 사용하지 않았다.

### qwen3:14b 비교 재시험

- GPU offload: `41/41 layers`
- `/api/ps size_vram`: 약 `9.64 GB`
- 같은 정상 통수: 약 `146초`
- 이전 CPU-only 정상 통수: 약 `324초`

과제와 실행 시점이 완전히 통제된 benchmark(성능시험)는 아니므로 정밀 성능
비율로 사용하지 않는다. 다만 CPU-only 병목이 해소됐다는 운영 확인에는 충분하다.

### qwen3.5:9b 구조화 출력 수리와 재시험

첫 실행에서는 후보 생성 뒤 JSON Schema 관할 호출이 빈 응답으로 끝났다. 서버
로그상 모델은 토큰을 생성했지만 thinking(내부 사고 출력)만 소비하고 최종 응답을
비웠다. Ollama payload에 `think=false`를 명시하도록 backend를 수정했다.

재시험 결과:

- 저장 크기: `6.6 GB`
- parameter size: `9.65B`
- quantization: `Q4_K_M`
- `/api/ps size_vram`: `5,389,387,038 bytes`
- 후보 생성 성공
- 관할 `applicable=true`
- 구조화 Review `reject`
- ReviewBatch `dependent_core_blocked`
- Gate 1 시작 성공
- 총 실행: 약 `65.5초`
- 사건 원장: `runs/operational-smoke-qwen3.5-9b-igpu-retest.jsonl`

이 결과로 `qwen3.5:9b`를 정 생성기 기본 확정 모델로 채택했다.

### 경계

이 시점에는 나머지 여섯 로컬 심사 모델이 미설치 상태였다. 이후
`phi4-reasoning:14b` 논리 심사관은 설치·구조화 출력·iGPU 실시험을 마쳤다.

[Ollama가 Vulkan 대신 CPU를 선택하거나 `/api/ps size_vram=0`이 되면 iGPU 연결
성공 판정을 폐기하고 환경변수·드라이버·서버 재시작 상태부터 재점검한다.]

## 2026-06-23 — qwen3:14b 단일 실모델 연기시험

목적은 모델 품질 순위나 발견률 측정이 아니라, 실제 Ollama 응답이 현재 구조화
출력 계약과 전체 입구 배관을 통과하는지 확인하는 것이었다.

### 환경

- Harness: `v0.12.0`
- Python: `3.14.4`
- Ollama API: `http://127.0.0.1:11434`
- 모델: `qwen3:14b`
  - parameter size: `14.8B`
  - quantization: `Q4_K_M`
  - 저장 크기: 약 `9.28 GB`
- 역할 배치:
  - 정 생성기: `qwen3:14b`
  - 논리 심사관: `qwen3:14b`
- 필수 측면: `logic`

같은 모델을 두 역할에 사용했으므로 이 시험은 cross-lineage(다른 학습 계통)
독립성 검증이 아니다.

### 정상 방향 통수

```text
실제 모델 후보 생성
→ 논리 관할 판정
→ 구조화 Review
→ Review 의미 계약
→ ReviewBatch 파생 상태 재계산
→ Gate 1 awaiting_review
```

결과:

- 후보 생성 성공
- 관할 `applicable=true`
- Review `pass_to_next_gate`
- ReviewBatch `clear`
- Gate 1 `awaiting_review`
- 사건 4개 모두 `event_id` 보유
- Gate 원장 재조회 성공
- 실행 시간: 약 `324초`

사건 원장:

- `runs/operational-smoke-qwen3-14b.jsonl`

### 결함 방향 통수

순환논증 미끼 `logic-circular-001` 한 건을 같은 모델에 투입했다.

결과:

- 결함 유형 `순환논증`
- Review `reject`
- `defect_found=true`
- ReviewBatch `dependent_core_blocked`
- 미끼 적발 사건 기록 성공
- 실행 시간: 약 `112초`

이는 단건 배관 확인이며 일반 발견률이나 성능 비율을 뜻하지 않는다.

### 가속 상태

Ollama `/api/ps` 응답:

```text
size_vram = 0
```

현재 `qwen3:14b`는 iGPU가 아니라 CPU에서 실행됐다.

추가 확인:

- `ipex-llm` Python package 없음
- `conda` 명령 없음
- Intel oneAPI 기본 설치 경로 없음
- Ollama 실행 파일은 설치돼 있으나 현재 PowerShell `PATH`에는 없음
- Ollama 앱과 로컬 API 서비스는 실행 중

### 당시 판정

기능 배관은 실모델에서도 정상이다. 그러나 CPU-only 상태의 `qwen3:14b`를 여러
역할에 순차 배치하면 한 후보 처리 시간이 크게 늘어난다.

따라서 다음 순서는 역할별 모델 확대가 아니라 iGPU 가속 연결 가능성 확인이다.
가속 연결이 실패하면 작은 모델을 배관 시험용으로 사용하되, 그 결과를 독립성이나
심사 품질 검증으로 해석하지 않는다.

[Ollama 또는 대체 backend에서 실제 GPU 메모리 사용이 확인되면 CPU-only 운영
판정을 재검토한다.]

위 조건은 같은 날 Vulkan iGPU 연결과 실제 VRAM 사용 확인으로 충족돼 CPU-only
판정은 폐기됐다.
