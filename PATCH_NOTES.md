# 패치노트

## v0.15.1 — Probe 정답 계약과 20문항 회귀 복구

- GitHub·Zenodo 공개 패키지 신설
  - GitHub용 README, CITATION.cff, `.zenodo.json`, 공개 체크리스트
  - Zenodo 설계 공개 PDF v1.1
  - 코드 스냅샷 ZIP과 SHA-256 목록
- 예약 DOI `10.5281/zenodo.20814616` 반영
- 공개 저장소 URL 반영:
  `https://github.com/chlgustj0512/LLM-Review-Harness-With-Recycling`
- 혼합 라이선스 확정
  - 소프트웨어 코드: Apache License 2.0
  - 설계 PDF·문서: CC BY 4.0
- 포괄적 서열 표현인 `우월/우월성`을 측정 가능한 `더 나은 평가 성능/비교 성능 향상`으로 교체
- 실모델 20문항 결과를 엄격 정답 계약으로 재기록
  - 결함 14/14 탐지
  - 정상 4/6 무결함 판정
  - 정상 관할 미진입 1건을 성공에서 제외
  - 엄격 정답 17/20
- Probe에 `expected_detected` 정답 필드 추가
  - 결함 문항: `true`
  - 정상 통제문항: `false`
- ProbeResult에 `correct`, `expected_detected` 기록
- 정상 통제문항은 단순 미탐지가 아니라 필수 관할 심사가 완료된 `clear`일 때만 정답
- CLI 요약에 `correct`, `all_correct` 추가
- `probe` 종료코드는 “전부 오류로 탐지”가 아니라 “전부 기대 정답과 일치”를 기준으로 판정
- Mock backend의 20문항 판정 범위 보강
  - 숨은 전제, 애매어, 양화사 오류, 거짓 유추, 정의역 누락, 필요·충분조건 혼동
  - 정상 빈 목록 코드의 `if not values` 보호절을 오탐하지 않도록 수정
  - 모든 보편명제를 범위 과장으로 오탐하지 않도록 경험적 적용 주장에 한정
- 정상 scope 문항의 관할 인식에 `일반화` 표지 추가
- 회귀검증의 기존 “모든 probe는 detected=true” 가정을 정답 계약 기반으로 교체

## v0.15.0 — Final Delivery Packet

- Gate 3 `accepted_synthesis` 완료 후보만 최종 제출 가능
- 승인 사건·최종 후보·최종 Review를 Event Contract로 재결속
- 승인 이후 OLMo 사후 감사를 새로 실행
  - 초기 후보 감사 재사용 금지
- 제출 상태:
  - `ready_clear`
  - `ready_with_advisory`
  - `ready_audit_failed`
- 승인된 한국어 본문은 감사 보고서와 분리해 보존
- 감사 결함이 있으면 한국어 보강 보고서를 별도 첨부
- 감사 실패 시 본문은 내보내고 실패 설명을 명시
- 기존 심사관별 판정·근거 요약 포함
- `export-delivery` CLI:
  - JSON·Markdown 파일 동시 생성
  - 같은 Gate flow 중복 생성 금지
- `show-delivery` CLI:
  - delivery ID 또는 flow ID 조회
  - 조회마다 사건 계약 재검증
- 파일 두 개가 모두 기록된 뒤에만 `final_delivery_packet_created` 사건 생성
- 파일 쓰기 실패 시 부분 파일 제거·완료 사건 미기록
- 실운전 제출 묶음:
  - `runs/deliveries/delivery-9d624842db5a.json`
  - `runs/deliveries/delivery-9d624842db5a.md`
- 자동 테스트: 133/133 통과
- Python `compileall`: 통과

## v0.14.0 — 비차단 OLMo 사후 감사와 제한형 논증 결함 테스트

- `confirmed-local`에 사후 감사 배관 추가
  - 번역: `qwen3.5:9b`
  - 영어 감사: `olmo2:13b`
- 기존 한국어 후보와 Gate 결과는 변경하지 않음
- 영어 정규화본만 OLMo를 거치며 결함이 있을 때 한국어 보강 보고서 생성
- 감사 결과는 항상 `non_blocking=true`
- 번역·감사 실패 시 `post_review_audit_failed` 사건만 기록하고 본 흐름 유지
- 번역→감사→한국어 보고서 출처를 Event Contract로 결속
- 기존 궤변생성기를 제한형 논증 결함 테스트케이스 생성기로 개편
- 허용 오류 8종만 생성
- `candidate_text`와 `hidden_oracle`을 생성 시점부터 분리
- 심사관에는 `candidate_text`만 전달
- 외부 시스템 공격·권한 우회·도구 실행·메모리 변조·사용자 조작·
  취약점 악용·사회공학 요청은 `OUT_OF_SCOPE`
- 실모델 논증 결함 사건:
  `runs/operational-argument-defect-generator.jsonl`
- 실모델 사후 감사 사건:
  `runs/operational-post-review-audit-olmo2.jsonl`
- `confirmed-local` 전체 진입점 자동 감사:
  `runs/operational-confirmed-local-post-audit.jsonl`
- 자동 테스트: 128/128 통과
- Python `compileall`: 통과

## 후속 후보 시험 — OLMo 2 13B 영어 내부 심사

- `olmo2:13b` 설치
- Intel Arc 140V `100% GPU`, 실행 메모리 `11 GB`
- 영어 정상안·개인정보 결함안·논리 전용 결함안 양방향 판정 확인
- `qwen3.5:9b` 한국어→영어 경계 번역에서 핵심 조건 보존 확인
- 판정 방향은 합격
- 영어 구조 계약과 관할 없는 법률명 자동 호출 문제 때문에 아직 미배치
- 운영 프로필은 계속 기존 값을 유지

## v0.13.4 — 사각지대 심사관 양방향 선발

- `glm4:9b` 설치 및 Intel Arc 140V `100% GPU` 적재 확인
  - architecture: `chatglm`
  - parameters: `9.4B`
  - quantization: `Q4_0`
  - 실행 크기: `5.4 GB`
- GLM은 개인정보를 수집하지 않는 정상안 3건을 모두 가상 위험으로 오탐
- 동일 Prompt(지시문)의 `qwen3.5:9b` 대조 시험:
  - 보호조치가 갖춰진 정상안: `applicable=true`, `pass_to_next_gate`
  - 무고지 직원 감시안: `applicable=true`, `reject`
- `confirmed-local`의 `blindspot_reviewer`를 `qwen3.5:9b`로 확정
- 사각지대 지시에 근거 없는 위험 상상과 구현 세부사항 과잉 요구 금지 추가
- `blindspot-workplace-surveillance-001` 기본 사건 미끼 추가
- Mock backend에 개인정보·동의·접근통제 누락 판정 추가
- Probe CLI가 수동 기본 모델명을 잘못 보고하던 문제 수정
  - 실제 `model_profile`과 reviewer별 실행 모델을 출력
- Probe CLI에서 심사관을 생략하면 등록 심사관 전원을 자동 실행
  - 일반 `run`의 논리·범위 기본값이 전체 미끼 검사에 잘못 재사용되던 연결 오류 수정
- 기본 사건 미끼: 8건
- Mock 전체 미끼: 8/8 적발
- 자동 테스트: 121/121 통과
- Python `compileall`: 통과

## v0.13.3 — Ministral 3 14B 범위 심사관 실배치

- `scope_reviewer` 배정을 `mistral-small3.2:24b`에서 `ministral-3:14b`로 변경
- `41/41 layers` full offload
- `/api/ps size_vram=8,664,698,060 bytes`
- 실제 Qwen 후보의 과도한 `모든 문의 채널` 범위를 `revise`로 적발
- 범위 심사 지시에 측정 과잉 방지 계약 추가
  - 범주형 경계와 사람 처리·되돌림 경로가 충분하면 임의 수치·절대 임계값 금지
- 관할 프롬프트에 reviewer 구체 검사 지시 포함
- 적용 조건·예외·실패 조건 누락 자체도 관할 대상임을 명시
- 보편 양화사·예외 없음·실패 조건 없음을 scope 관할로 고정
- 최종 정상 후보 `pass_to_next_gate`, `clear`
- 한국어 범위과장 미끼 `detected=true`, `reject`, `objections`
- `scope-universal-rollout-001` 기본 사건 미끼 추가
- 기본 사건 미끼: 7건
- Mock 회귀 판정기가 `예외는 없다`를 예외 존재로 오인하던 부정 표현 처리 수정
- 자동 테스트: 120/120 통과
- Python `compileall`: 통과

## v0.13.2 — 물리 심사관 연결과 관할/결함 분리

작성일: 2026-06-23  
성격: 물리 역할 연결, 관할 자가선별 근본 수리, 차원오류 미끼 추가

### 물리 심사관

- `llama3.1:8b` 설치
- `33/33 layers` full offload
- `/api/ps size_vram=5,263,327,231 bytes`
- Qwen 정상 물리 계산은 `pass_to_next_gate`, `clear`
- 운동에너지 차원오류 미끼는 `detected=true`, `reject`

### 관할 자가선별 수리

- 관할을 결함 발견 여부와 분리
- 담당 법칙·수식·주장·조건·단위·실행물이 있으면 `applicable=true`
- 실제 결함 판정은 다음 Review 단계에서만 수행하도록 프롬프트 명시
- 관할/결함 분리 문구 회귀 테스트 추가

### 회귀 기준

- `physics-kinetic-dimension-001` 기본 미끼 추가
- Mock backend에 물리 관할·차원오류 판정 추가
- 기본 사건 미끼: 6건
- 자동 테스트: 119/119 통과
- Python `compileall`: 통과

### 현재 경계

- 물리 Llama는 판정 방향은 맞았지만 설명 문장에 차원 모순이 남음
- 별도 정상 후보에서 불필요한 시간함수 조건을 요구한 사례 2건 존재
- 따라서 물리 역할은 조건부 실배치이며 최종 물리 근거로 단독 사용하지 않음
- 범위·사각지대 역할은 아직 식별자·크기 확인 단계

[물리 설명 모순이나 정상 후보 반대 판정이 반복되면 Llama 배정을 폐기한다.]

## v0.13.1 — GPT-OSS Harmony 호환과 수학 심사관 실배치

작성일: 2026-06-23  
성격: 수학 심사 모델 연결, structured output fallback, Windows UTF-8 출력 수리

### 수학 심사관

- `gpt-oss:20b` 설치
- `25/25 layers` full offload
- `/api/ps size_vram=11,577,935,789 bytes`
- Qwen의 잘못된 등차수열 합 `280`을 실제 값 `120`으로 교정
- 올바른 고정 계산은 `pass_to_next_gate`, `clear`
- 가짜해 `x=0` 미끼는 `detected=true`, `dependent_core_blocked`

### 출력 호환 수리

- JSON Schema 호출이 빈 응답이면 `format` 없이 1회 재시도
- fallback 결과도 기존 JSON parser와 Review 계약으로 동일 검증
- Windows CLI stdout·stderr를 UTF-8로 설정
- em dash 등 CP949 밖 문자가 최종 출력에서 실패하던 문제 해소

### 회귀 기준

- `math-extraneous-root-001` 기본 미끼 추가
- Mock backend에 수학 관할·가짜해 판정 추가
- JSON Schema 빈 응답 fallback 단위 테스트 추가
- 기본 사건 미끼: 5건
- 자동 테스트: 118/118 통과
- Python `compileall`: 통과

### 현재 경계

- 정·코드·논리·수학 역할 실운전 완료
- 물리·범위·사각지대 역할은 아직 식별자·크기 확인 단계
- GPT-OSS는 4K 문맥에서 검증했으며 장문 문맥 VRAM은 별도 검증 필요

[schema 없는 fallback에서도 JSON 계약 위반이 반복되면 해당 모델 배정을
재검토한다.]

## v0.13.0 — iGPU 연결과 확정 모델 프로필

작성일: 2026-06-23  
성격: 로컬 추론 가속 연결, 모델 식별자 정정, 실행 프로필 고정

### iGPU

- Intel Arc 140V를 Ollama Vulkan backend에 연결
- 사용자 환경변수 `OLLAMA_IGPU_ENABLE=1` 영구 설정
- `qwen3:14b` `41/41 layers` full offload 확인
- `qwen3.5:9b` `/api/ps size_vram=5.39GB` 확인
- IPEX-LLM을 추가 설치하지 않고 Ollama 내장 Vulkan 경로 사용

### 구조화 출력 호환 수리

- 모든 Ollama 호출 payload에 `think=false` 추가
- `qwen3.5:9b`가 JSON Schema 호출에서 사고 토큰만 생성하고 빈 최종 응답을
  반환하던 문제 해소
- 생성→관할→Review→ReviewBatch→Gate 1 실모델 통수 성공

### 확정 모델 프로필

- `harness.model_roster.CONFIRMED_LOCAL_PROFILE` 추가
- CLI `--model-profile confirmed-local` 추가
- 정 생성기 1개와 로컬 심사관 6개의 정확한 Ollama 태그 고정
- 명시적인 `--thesis-model`, `--adversary-model`, `--reviewer-model`은 프로필보다
  우선하도록 유지
- 궤변생성기는 7+1 구성원 밖의 공격 보조 역할로 분리

### 이름 정정

- `Qwen 3.6-A3B` → `qwen3.5:9b`
- `Gemma 4 12B` → `gemma4:12b`
- `Phi-4 Reasoning 14B` → `phi4-reasoning:14b`
- `GPT-OSS 20B` → `gpt-oss:20b`
- 존재하지 않는 `Llama 3.3 8B`와 과대 크기의 Llama 4 Scout
  → `llama3.1:8b`
- `Mistral Small 4 24B` → `mistral-small3.2:24b`
- `GLM available min` → `glm4:9b`
- 외부 재심 모델 → Claude Opus 4.8 / `claude-opus-4-8`

상세 명단과 근거: `MODEL_ROSTER.md`

### 검증

- `qwen3.5:9b` iGPU 실모델 통수: 약 65.5초
- 자동 테스트: 117/117 통과
- Python `compileall`: 통과
- 확정 프로필 역할 전수 배정·명시 override 회귀 테스트 추가

### 논리 심사관 실배치

- `phi4-reasoning:14b` 설치·구조화 출력 확인
- `41/41 layers` full offload
- `/api/ps size_vram=11,799,069,981 bytes`
- Qwen 정 생성→Phi 논리 심사의 정상 방향 약 `126.6초`
- Phi 순환논증 미끼 적발 방향 약 `43.6초`
- 미끼 `detected=true`, Review `reject`, Batch `dependent_core_blocked`

### 코드 심사관 실배치

- `gemma4:12b` 설치·구조화 출력 확인
- `49/49 layers` full offload
- `/api/ps size_vram=8,002,595,716 bytes`
- 생성기의 실행 코드 누락을 `revise`로 적발
- 실행 가능한 고정 정상 코드는 `pass_to_next_gate`, `clear`
- 빈 목록 `ZeroDivisionError` 미끼는 `detected=true`, `revise`
- `code-empty-average-001`을 기본 사건 단위 미끼에 추가
- Mock backend에 코드 관할과 해당 경계값 결함 회귀 판정 추가
- 같은 iGPU에서 별도 모델 요청을 병렬 실행하지 않는 운영 조건 기록

### 현재 경계

- 주모델 `qwen3.5:9b` 설치·실운전 완료
- 코드 심사관 `gemma4:12b` 설치·실운전 완료
- 논리 심사관 `phi4-reasoning:14b` 설치·실운전 완료
- 나머지 네 로컬 심사 모델은 공식 식별자·크기 확인 단계
- 모델 프로필은 자동 다운로드하지 않음

[모델이 구조화 출력 계약을 반복 위반하거나 단일 실행이 iGPU 메모리를 넘으면
해당 역할 배정을 폐기하고 fallback을 재선정한다.]

## v0.12.0 — 전체 배관 통합 통수 기준선

작성일: 2026-06-23  
성격: 골격 완공 후 처음부터 끝까지 이어지는 전체 흐름 검증

### 검사한 완결 물길

1. 정상 물길

```text
생성 → 다측면 심사 → Gate 1~3 → Ratchet → 종료 Snapshot
```

2. 결함 되먹임 물길

```text
궤변 → filter escape 후보 → 사람 확인 → 준비 승인
→ Block-rule 활성 → 다음 생성 문맥 주입
```

3. 외부 재심 물길

```text
심사 충돌 → Appeal 문서 → overturn 재입력 → Case 확인
→ Block-rule 활성 → 다음 생성 문맥 주입
```

4. 실패 재활용 물길

```text
reject Review → salvage intake → Library 정식화
→ 목적 승인 → 목적·조건 조회
```

### 결과

- 네 완결 물길 모두 첫 통수에서 성공
- 구성요소 사이의 신규 단절·역류·출처 불일치 없음
- 정상 종료 Snapshot에서 초기 챔피언 보존 확인
- confirmed 전·명시 승인 전에는 되먹임이 열리지 않는 기존 밸브 유지
- Library 목적 승인 전 검색 차단과 승인 후 검색 노출 확인
- 외부 Appeal 문서 파일 생성과 재입력 사건 사슬 확인

### 추가 검증

- 전체 자동 테스트: 113/113 통과
- Python `compileall`: 통과
- CLI 전체 명령 등록 확인
- 실제 `python -m harness ... run --backend mock` 실행 성공
- Mock CLI에서 생성→심사→Gate 1 시작 사건 출력 확인

### 문서 정정

- 구현 범위를 Reviewer Orchestrator까지만으로 표시하던 오래된 서술 수정
- 부정예시 되먹임을 shadow 전용으로 표시하던 오래된 서술 수정
- 현재 회귀 기준선을 113개로 갱신
- 로컬 역할 자리는 정 1개 + 심사관 6개이며 기본 활성 심사관은 2개임을 명시

### 현재 경계

- 전체 배관의 기능 연결은 검증됐지만 실제 7계통 모델 배치는 아직 하지 않음
- Gate 단계별 Hard Gate·절대 Rubric은 아직 수동 판정 자리
- 컴파일러·테스트 러너·SymPy·차원검산 Hard verifier는 아직 미연결
- 블라인드 재투입은 외부 Appeal 배관과 별개로 아직 미구현

### 후속 운영 연기시험

`qwen3:14b` 단일 실모델로 다음을 확인했다.

- 실제 생성→논리 관할→심사→Gate 1 시작 성공
- 순환논증 미끼 1건 `reject·dependent_core_blocked` 성공
- 구조화 출력과 Review·ReviewBatch 계약 통과
- Gate 원장 재조회와 사건 ID 무결성 확인
- 전체 회귀검증 113/113 유지

운영 제약:

- 정상 실행 약 324초
- 순환논증 미끼 약 112초
- Ollama `/api/ps`의 `size_vram=0`으로 CPU-only 실행 확인
- `ipex-llm`·conda·oneAPI 설치 흔적 없음

상세 기록: `OPERATIONS.md`

## v0.11.2 — ReviewBatch 파생 상태 재계산 검증

작성일: 2026-06-23  
성격: 2차 전체 감사의 심사 묶음 상태 변조 수리

### 수정한 오류

- 실제 Review에 반대 판정이 있는데 Batch `status="clear"`로 저장할 수 있던 문제
- `conflicting_aspects`·`empty_aspects`·`dependent_core_blocked`를 원본과 다르게
  저장해도 Gate가 신뢰하던 문제
- 관할이 `applicable=true`인데 해당 reviewer의 Review가 누락될 수 있던 문제
- 다른 후보의 Review를 현재 ReviewBatch에 넣을 수 있던 문제
- 생성 시 상태 계산과 저장 원장 재생 시 검증 규칙이 서로 다른 위치에 있던 문제

### 구현

- `derive_review_batch_state()`를 공통 파생 상태 계산기로 추가
- 다음 값을 관할·개별 Review에서 재계산
  - `empty_aspects`
  - `conflicting_aspects`
  - `dependent_core_blocked`
  - 최종 `status`
- Reviewer Orchestrator(심사관 조정계층)가 공통 계산기로 Batch를 생성
- Candidate Registry(후보 원장)가 저장된 Batch를 같은 계산기로 재검증
- 적용 관할과 Review를 reviewer·aspect 쌍으로 결속
- Batch candidate ID와 각 Review candidate ID를 결속
- 축약 테스트 사건을 실제 ReviewBatch 계약 형태의 공통 fixture로 교체

### 상태 우선순위

```text
conflict
→ empty_aspect
→ human_review
→ dependent_core_blocked
→ objections
→ clear
```

이 순서는 기존 동작을 바꾸지 않고 한 곳에서만 정의한다.

### 회귀·통수 검증

- 변경 전 기준선: 106/106 통과
- 상태 위조·Review 누락·후보 바꿔치기 재현 3건 추가
- 최종 전체: 109/109 통과

## v0.11.1 — Review 판정·결함 의미 계약

작성일: 2026-06-23  
성격: 2차 전체 감사 잔여 의미 모순 수리

### 수정한 오류

- `reject`·`revise`인데 `defect_found=false`인 심사가 허용되던 문제
- 결함을 발견했다고 했지만 결함 유형·위치가 비어 있는 문제
- `revise`인데 실제 수정 요구사항이 없는 문제
- 결함 미발견 상태에 결함 상세를 함께 기록할 수 있던 문제
- 정상 API를 우회해 원장에 직접 삽입된 모순 Review를 Gate가 출처로 사용할 수
  있던 문제

### 구현

- `validate_review_semantics()`를 Review 의미 계약의 단일 규칙으로 추가
- 모델 출력 직후 `Review.from_dict()`에서 검증
- 저장된 `review_batch_completed`를 Candidate Registry가 다시 읽을 때 동일 규칙으로
  재검증
- 일반 심사·Gate 수정본 재심사·궤변 심사가 기존 `Review.from_dict()` 경로를
  공유하므로 세 경로에 동일하게 적용
- 심사 프롬프트에 verdict와 `defect_found`의 대응 규칙 명시

### 유도리 규칙

`needs_human_review`는 판정불능 상태이므로 `defect_found`를 한쪽으로 강제하지 않는다.
결함을 실제 특정했으면 `true`와 상세를 기록하고, 정보 부족으로 특정하지 못했으면
`false`와 빈 상세를 기록한다.

### 회귀·통수 검증

- 변경 전 기준선: 100/100 통과
- 의미 모순 조합 및 원장 직접 삽입 재현 6건 추가
- 최종 전체: 106/106 통과

## v0.11.0 — 공통 Event Contract Validator 도입

작성일: 2026-06-23  
성격: 2차 전체 감사의 반복 근본 원인 제거

### 판단

이전 패치들은 각 원장의 쓰기 API를 강화했지만, JSONL에 직접 삽입된 사건을
조회할 때 저장 payload를 그대로 신뢰하는 경로가 남아 있었다. Gate 3 재심 결속
오류를 먼저 단독 수리한 뒤, 같은 원인의 잔여 오류는 개별 패치가 아니라 공통
Event Contract Validator(사건 계약 검증기)로 이관했다.

### 구현

- `harness/event_contracts.py`에 공통 사건 계약 검증기 추가
- 사건 조회·재생 시 저장된 결과값을 신뢰하지 않고 원본 사건과 현재 상태에서
  기대값을 다시 계산
- 다음 5개 원장에 연결
  - Gate: stage·status·candidate·review source·decision 전이 검증
  - Library: 목적 승인과 Review/Appeal intake 출처 사슬 검증
  - Case: 확인 상태·Block-rule·Appeal case 원본 결속 검증
  - Ratchet: Gate admission·comparison·finalize·champion update 검증
  - Snapshot: 종료 시점 champion과 source finalize 사건 검증
- Ratchet 측면 비교 입력 순서와 무관하게 `priority_line` 순서로 champion update를
  기록하도록 결정론화
- 구버전 conflict Gate가 `awaiting_review`로 저장된 한 가지 형태만 제한적으로
  호환하고, 새 사건의 임의 상태 위조는 허용하지 않음

### 차단한 변조 경로

- Gate 사건의 `next_stage=99`·허위 완료 상태
- 존재하지 않는 출처를 붙인 Library 목적 승인
- 원본 Review에 없는 보존 부품의 내부 intake
- 계산된 규칙과 다른 부정예시 Block-rule
- finalize 근거 없이 삽입된 Ratchet champion update
- 실제 champion과 다른 종료 Snapshot
- Appeal 결과·packet과 다른 Case 내장 내용

### 회귀·통수 검증

- 변경 전 기준선: 95/95 통과
- 공통 검증기 연결 후: 95/95 통과
- 변조 재현 5건 추가 후 최종 전체: 100/100 통과

## v0.10.9 — Gate 3 외부 재심 결과 결속

작성일: 2026-06-23  
성격: 2차 전체 감사 최우선 오류 수리

### 수정한 오류

- Gate 3에서 외부 재심 결과 없이 최종 승인할 수 있던 문제
- 재심 요청 후 결과 없이 수정·거절로 상태를 닫을 수 있던 문제
- 외부 재심이 `overturn`이어도 그대로 최종 승인할 수 있던 문제
- `uncertain` 결과를 무시하고 최종 승인할 수 있던 문제

### 결과별 규칙

```text
결과 없음
→ 승인 / 수정 / 거절 모두 금지

uphold
→ 사람이 승인 / 수정 / 거절 가능

uncertain
→ 승인 금지, 수정 / 거절 가능

overturn + case unconfirmed
→ 승인 금지, 수정 / 거절 가능

overturn + case confirmed
→ 승인 금지, 수정 / 거절 가능

overturn + case dismissed
→ 사람이 승인 / 수정 / 거절 가능
```

### 결속 검증

- Gate decision의 appeal ID
- Gate candidate ID
- source review event ID
- appeal packet event ID
- appeal result의 source event ID
- overturn case ID와 현재 confirmation 상태

### 유도리 원칙

외부 재심의 `overturn`을 자동 영구 거절로 사용하지 않는다. 독립 확인에서 결함이
재현되지 않아 Case가 `dismissed`되면 사람이 최종 승인할 수 있다.

### 회귀·통수 검증

- 변경 전 기준선: 90/90 통과
- 중간 검증: 94/94 통과
- 최종 전체: 95/95 통과

## v0.10.8 — 내부 Review 보존 부품 입고 연결

작성일: 2026-06-23  
성격: 내부 심사–지연 재사용 라이브러리 단절 수리

### 점검 결과

- 내부 `Review`에는 `salvageable_part` 필드가 없었음
- 메타 미완성 라이브러리 입고는 외부 Appeal 결과에서만 가능했음
- 내부 심사가 후보의 결함과 유효 부품을 함께 발견해도 유효 부품이 유실됐음

### 구현

- Review JSON schema·프롬프트·모델에 `salvageable_part` 추가
- 일반 심사·Gate 수정본 재심사·궤변 심사에서 공통 입고 처리
- 입고 사건에 다음 출처 저장
  - candidate ID
  - review/report event ID
  - reviewer ID
  - aspect
  - verdict
  - source kind

### 허용 규칙

```text
defect_found=true
+ verdict=reject 또는 revise
+ salvageable_part 비어 있지 않음
→ 메타 미완성 입고
```

`pass_to_next_gate·needs_human_review` 또는 결함 없는 심사가 보존 부품을
제출하면 Review 검증 단계에서 거부한다.

### 지연 재사용 원칙

- `metadata_status=incomplete`
- `purpose_status=missing`
- `searchable=false`
- 자동 목적 추론 금지
- 자동 정식 부품 등록 금지
- 자동 합성 금지

### 회귀·통수 검증

- 변경 전 기준선: 86/86 통과
- 중간 검증: 90/90 통과
- 최종 전체: 90/90 통과

## v0.10.7 — Ratchet 목적 범위와 후보 과제 결속

작성일: 2026-06-22  
성격: 통합 점검에서 발견한 무관 목적 후보 입장 수리

### 수정한 오류

- Gate만 통과하면 전혀 다른 과제의 후보도 같은 래칫에 들어가던 문제
- 서로 비교 불가능한 후보가 전체·측면 챔피언을 바꿀 수 있던 문제
- 입장 사건의 task 정보가 Gate 출처와 재검증되지 않던 문제

### 범위 결속 방식

첫 입장 후보의 Task 목표와 제약을 세션 비교 규격으로 고정한다.

```text
첫 accepted 후보
→ task goal + constraints 추출
→ Ratchet scope 결속

후속 accepted 후보
→ task goal + constraints 추출
→ scope 정확 일치 확인
→ 입장 또는 거부
```

### 유도리 게이트 적용

- 의미 유사도 모델 미사용
- 유사도 점수·임계값 미사용
- 공백·대소문자 정규화만 적용
- 제약 순서는 무시하되 내용은 정확히 같아야 함
- task ID가 달라도 같은 과제 범위면 비교 가능

### 추적·변조 방어

- 입장 사건에 task ID·목표·제약 저장
- 상태 재구성 시 Gate flow의 실제 task와 재대조
- 후보 ID와 Gate 최종 후보 일치 확인
- 구버전 사건은 Gate 출처에서 task scope를 복원
- 수동 삽입된 무관 후보는 조회 단계에서도 거부

### 회귀·통수 검증

- 변경 전 기준선: 82/82 통과
- 중간 검증: 85/85 통과
- 최종 전체: 86/86 통과

## v0.10.6 — 궤변 심사 판정불능 분류 분리

작성일: 2026-06-22  
성격: 통합 점검에서 발견한 필터 적발 오분류 수리

### 수정한 오류

- `empty_aspect`를 필터가 결함을 잡은 것으로 기록하던 문제
- `conflict`를 필터가 결함을 잡은 것으로 기록하던 문제
- `human_review`를 필터 성공으로 볼 수 있던 문제
- 구버전 오분류 로그가 장기 조회에서 계속 적발 사건으로 보이던 문제

### 분류 규칙

```text
clear
→ filter_escape_candidate

objections / dependent_core_blocked
→ caught_by_filter

conflict / empty_aspect / human_review
→ review_inconclusive
```

### 의미

- `caught_by_filter`: 심사관이 reject·revise 결함을 실제 제시함
- `filter_escape_candidate`: 심사는 통과했으나 숨은 결함 여부 미확정
- `review_inconclusive`: 심사 자체가 완료되지 않아 적발·통과 판단 불가

### 후속 처리

- 판정불능 사건도 원문·심사 결과를 보존
- 해당 원인에 맞는 외부 Appeal 생성 가능
- `adversary_review_inconclusive` 사건으로 원인과 Appeal ID 연결
- 판정불능 사건을 `confirmed` 결함으로 직접 승격 금지

### 구버전 호환

구버전 사건이 `caught_by_filter`이면서 심사 상태가
`conflict·empty_aspect·human_review`이면 조회 시:

- `reported_disposition=caught_by_filter` 보존
- 현재 `disposition=review_inconclusive`로 교정
- 원 JSONL 사건은 수정하지 않음

### 회귀·통수 검증

- 변경 전 기준선: 77/77 통과
- 중간 검증: 81/81 통과
- 최종 전체: 82/82 통과

## v0.10.5 — Library 출처 사건과 후보 결속

작성일: 2026-06-22  
성격: 통합 점검에서 발견한 라이브러리 출처 바꿔치기 수리

### 수정한 오류

- 존재하는 event ID만 제시하면 무관한 candidate ID를 출처로 주장할 수 있던 문제
- 후보를 포함하지 않는 사건도 라이브러리 출처로 사용할 수 있던 문제
- 이미 저장된 변조 부품이 조회·승인 단계에서 재검증되지 않던 문제

### 결속 규칙

```text
source_event_id 조회
→ 지원하는 후보 출처 사건인지 확인
→ 사건 내부 candidate ID 추출
→ source_candidate_id와 정확 일치
→ library_part_proposed
```

### 허용 출처 사건

- `review_batch_completed`
- `gate_decision_recorded`
- `appeal_packet_created`
- `appeal_result_recorded`
- `filter_escape_case_reported`
- `appeal_overturn_case_reported`
- `library_intake_candidate_recorded`

### 안전 조건

- 후보 ID 불일치 시 저장 거부
- 후보 출처가 없는 사건은 저장 거부
- 중첩된 Case candidate 출처도 명시적으로 추출
- `get·approve_purpose·query` 경로에서 저장된 출처를 재검증
- 구버전·수동 변조 부품도 출처가 틀리면 노출 금지

### 회귀·통수 검증

- 변경 전 기준선: 73/73 통과
- 중간 검증: 77/77 통과
- 최종 전체: 77/77 통과

## v0.10.4 — Appeal overturn과 사건 확인 흐름 연결

작성일: 2026-06-22  
성격: 통합 점검에서 발견한 외부 재심–Case 단절 수리

### 수정한 오류

- 외부 재심이 `overturn`이어도 확인 가능한 case가 생성되지 않던 문제
- 재심 결함이 기존 확인·부정예시 승인 배관으로 들어가지 못하던 문제
- 위조된 외부 재심 case가 원장에 들어올 수 있던 문제

### 새 흐름

```text
appeal_result_recorded(verdict=overturn)
→ appeal_overturn_case_reported
→ unconfirmed
→ confirm-case로 confirmed / dismissed
→ 준비 승인
→ 부정예시 활성 승인
```

### 자동확정 금지

- `overturn`은 결함 확정이 아니라 사건 후보 등록
- `uphold·uncertain`은 사건 후보를 만들지 않음
- `confirmed` 후에도 자동 되먹임 금지
- 준비 승인과 사건별 활성 승인이 있어야 Block-rule 사용

### 출처 결속

Case 원장은 다음을 원본 `appeal_result_recorded` 사건과 대조한다.

- appeal result event ID
- appeal ID
- candidate ID
- case ID
- verdict=`overturn`

하나라도 다르면 조회·확인을 거부한다.

### 회귀·통수 검증

- 변경 전 기준선: 71/71 통과
- 중간 검증: 73/73 통과
- 최종 전체: 73/73 통과

## v0.10.3 — Gate 3 사람 검토와 외부 재심 연결

작성일: 2026-06-22  
성격: 통합 점검에서 발견한 Gate–Appeal 단절 수리

### 수정한 오류

- Gate 3에서 `needs_human_review`를 기록해도 재심 문서가 생성되지 않던 문제
- Gate 상태와 Appeal packet 사이에 추적 가능한 결속이 없던 문제
- 재심 문서 없이 Gate 3을 사람 검토 상태로 바꿀 수 있던 문제
- 잘못된 Gate 요청에서도 고아 Appeal 문서가 먼저 생성될 수 있던 문제

### 새 흐름

```text
Gate 3 needs_human_review 요청
→ 결정 가능 여부 사전검증
→ Gate 전용 Appeal packet·Markdown 생성
→ gate_decision_recorded.appeal_id 저장
→ gate_appeal_connected 사건 저장
→ awaiting_human_review
```

### 결속 키

- Gate flow ID
- candidate ID
- task ID
- source review event ID
- Gate decision event ID
- appeal ID

하나라도 현재 Gate 상태와 다르면 연결을 거부한다.

### 안전 조건

- Gate 3 전용 Appeal 없이 `needs_human_review` 금지
- 다른 후보·과제·Gate·심사 사건의 Appeal 재사용 금지
- 다른 Gate 결정에 `appeal_id` 삽입 금지
- 결정 사전검증 실패 시 문서와 사건을 생성하지 않음

### 회귀·통수 검증

- 변경 전 기준선: 68/68 통과
- 중간 검증: 69/69, 70/70 통과
- 최종 전체: 71/71 통과

## v0.10.2 — 심사 상태와 Gate 결정 결속

작성일: 2026-06-22  
성격: 통합 점검에서 발견한 미해결 심사 우회 경로 수리

### 수정한 오류

- `conflict·empty_aspect·human_review`인데 일반 Gate 상태로 시작하던 문제
- 도구가 사람 검토 대기 상태를 해소할 수 있던 문제
- `dependent_core_blocked` 후보가 다음 Gate로 통과할 수 있던 문제
- Gate 1의 사람 검토 상태에서 Gate 3 최종 승인으로 건너뛸 수 있던 문제
- 구버전 로그의 미해결 심사 상태가 새 규칙을 우회할 수 있던 문제

### 상태별 처리

```text
clear                  → 기존 Gate 흐름
objections             → 명시적 판단으로 통과 가능
dependent_core_blocked → revise / reject만 가능
conflict               → awaiting_human_review
empty_aspect           → awaiting_human_review
human_review           → awaiting_human_review
```

독립 측면의 반대까지 일괄 봉쇄하지 않는다. 종속핵심 결함과 검토 자체가
미완료된 상태만 강제 차단한다.

### 사건 추적

- Gate 결정 사건에 `source_review_status` 추가
- 수정 후보 사건에 재진입 상태 `next_status` 추가
- 사람 해소 사건은 candidate·review event가 같은 경우에만 후속 Gate에서 인정

### 회귀·통수 검증

- 변경 전 기준선: 61/61 통과
- 중간 검증: 67/67 통과
- 최종 전체: 68/68 통과

## v0.10.1 — Candidate Registry·수정 후보 재심사 결속

작성일: 2026-06-22  
성격: 통합 점검에서 발견한 Gate 우회 경로 수리

### 수정한 오류

- 존재하지 않는 candidate ID를 수정본으로 제출할 수 있던 문제
- 다른 task의 후보를 현재 Gate에 연결할 수 있던 문제
- 수정 후보가 새 심사를 받지 않고 동일 Gate로 복귀할 수 있던 문제
- 수정 뒤에도 Gate가 최초 후보의 review event를 계속 가리키던 문제

### 구현

- `CandidateRegistry`
  - task·candidate·review event 존재 확인
  - candidate와 task 결속 확인
  - review event와 candidate 결속 확인
  - `task → candidate → review` 사건 순서 확인
- `GateLedger.start`와 `submit_revision`에서 위 결속을 강제
- 수정 사건에 `source_review_event_id` 저장
- 수정 후 Gate 상태가 최신 심사 사건을 가리키도록 변경
- `submit-gate-revision` CLI를 raw ID 연결에서 다음 안전 흐름으로 교체

```text
수정문 입력
→ 새 candidate 등록
→ reviewer 재심사
→ review_batch_completed 기록
→ 같은 Gate 단계로 복귀
```

### 회귀·통수 검증

- 변경 전 기준선: 57/57 통과
- 중간 통합 검증: 60/60 통과
- 최종 전체: 61/61 통과

## v0.10.0 — 종료 승인·잠정 챔피언 Snapshot·메타게임 전이

작성일: 2026-06-22  
기준 설계서: §14, Part VI 잔여 보류

### 목적

래칫에서 어느 측면도 개선되지 않은 최근 비교를 종료 가능 신호로 만들고,
명시적 승인 후 현재 챔피언을 잠정 Snapshot으로 고정한다. 환경 변화 시 삭제하지
않고 `deprecated`로 보존하며 재소환할 수 있게 한다.

### 종료 가능 조건

```text
최근 비초기 후보 평가 완료
+ pending 후보 없음
+ 모든 우선순위 측면 비교 존재
+ improved 측면 0개
→ termination_eligible
```

`regressed`와 `no_meaningful_change`는 모두 “개선 없음”에 포함한다.

### 추가

- `TerminationLedger`
- `ChampionSnapshot`
- `MetagameTransitionEvent`
- CLI
  - `check-ratchet-termination`
  - `approve-ratchet-termination`
  - `show-champion-snapshot`
  - `change-metagame-status`
- 이벤트
  - `ratchet_termination_approved`
  - `metagame_status_changed`

### Snapshot 내용

- 래칫 세션·목적
- 사용자 우선순위 줄
- 전체 챔피언 candidate ID
- 측면별 챔피언 candidate ID
- 종료 근거
- 종료를 가능하게 한 finalize event ID
- 현재 메타게임 상태

### 메타게임 상태

```text
active ↔ deprecated
```

- `deprecated`는 삭제가 아니라 잠듦
- 재소환은 동일 Snapshot을 `active`로 되돌리는 새 사건
- 상태 전이 중 챔피언 맵 수정 금지

### 측정 과잉 차단

- 변화점 자동 탐지 미구현
- 문헌 발행률 감시 미구현
- 종료 점수·횟수 임계값 없음
- 사람·도구의 근거 있는 종료 승인과 환경 변화 통보만 사용

### 안전 조건

- 첫 초기 챔피언만으로 종료 불가
- `improved` 측면이 하나라도 있으면 종료 불가
- pending 후보가 있으면 종료 불가
- 종료 승인 중복 금지
- 종료된 래칫 세션에 새 후보 입장 금지
- 현재와 같은 메타게임 상태로 중복 전이 금지
- Snapshot의 챔피언 내용은 불변

### 회귀·통수 검증

- 변경 전 기준선: 50/50 통과
- 변경 후 전체: 57/57 통과
- 명시적 회귀 계약: 8/8 통과
- 격리 Python 캐시에서 `compileall` 통과
- 개선 측면 존재 시 종료 차단
- 개선 0개일 때 종료 가능 신호 확인
- 종료 승인 후 Snapshot 생성
- 종료 후 새 후보 입장 차단
- `active → deprecated → active` 재소환
- 상태 전이 후 챔피언 보존

CLI 통수 결과:

```text
termination_eligible: true
snapshot: active
→ deprecated
→ active
champions_preserved: true
```

### 현재 경계

- 종료 Snapshot의 측면별 챔피언을 라이브러리 부품으로 자동 분해하지 않는다.
- 변화점 탐지 프로그램은 사람 통보로 충분하므로 보류한다.
- 다음 단계는 전체 배관 연결 상태를 점검하고, 아직 자리만 있고 연결되지 않은
  경로를 메우는 통합 감사가 적합하다.

## v0.9.0 — 사전식 상대 래칫 + 측면별 챔피언

작성일: 2026-06-22  
기준 설계서: §10-2, §14

### 목적

Gate 통과 후보끼리 절대 점수 없이 이전 챔피언 대비 상대 변화만 기록하고,
사용자가 정한 우선순위 줄로 전체 챔피언을 갱신한다. 전체 선택과 별개로
측면별 최고 부품도 보존한다.

### 추가

- `RatchetLedger`
- `RatchetSessionState`
- `RatchetComparisonEvent`
- 사용자 지정
  - 목적
  - 우선순위 측면 줄
- 상대 변화 판정
  - `improved`
  - `no_meaningful_change`
  - `regressed`
- 전체 챔피언
- 측면별 챔피언
- CLI
  - `start-ratchet`
  - `show-ratchet`
  - `admit-ratchet-candidate`
  - `record-ratchet-comparison`
  - `finalize-ratchet-candidate`
- 이벤트
  - `ratchet_session_started`
  - `ratchet_candidate_admitted`
  - `ratchet_comparison_recorded`
  - `ratchet_candidate_finalized`
  - `ratchet_champion_updated`

### 진입 조건

- Gate flow가 `completed_accepted`여야 함
- Gate 최종 decision event를 출처로 보존
- 동일 candidate 중복 진입 금지
- 한 세션에 pending 후보 하나만 허용

### 사전식 전체 판정

우선순위가 `logic > scope > reuse`일 때:

1. `logic`이 `improved` 또는 `regressed`면 거기서 전체 결과 결정
2. `logic`이 `no_meaningful_change`일 때만 `scope`로 이동
3. 첫 비중립 결과 이후의 낮은 측면은 전체 결과를 뒤집지 못함

모든 측면 결과는 측면별 챔피언 갱신을 위해 별도 보존한다.

### 측정 과잉 차단

- 절대 점수 없음
- 가중합 없음
- ε 또는 동률밴드 없음
- “유의미한 변화”의 수치 임계값 없음
- 상대 판정 주체·이유만 사건으로 기록

### 회귀·통수 검증

- 변경 전 기준선: 43/43 통과
- 변경 후 전체: 50/50 통과
- 명시적 회귀 계약: 7/7 통과
- 격리 Python 캐시에서 `compileall` 통과
- Gate 미완료 후보 진입 차단
- 첫 후보의 전체·측면 초기 챔피언 설정
- 상위 측면 후퇴 시 하위 개선이 전체 결과를 뒤집지 않음
- 하위 개선의 측면별 챔피언 보존
- 상위 중립 시 다음 측면 개선으로 전체 챔피언 갱신
- 비교 미완료 상태의 finalize 차단
- pending 후보 중복 입장 차단

CLI 통수 결과:

```text
후보 1: 전체·logic·scope 초기 챔피언
후보 2: logic regressed / scope improved
결과:
  전체 챔피언 = 후보 1
  logic 챔피언 = 후보 1
  scope 챔피언 = 후보 2
```

### 현재 경계

- 상대 변화 판정은 자동 생성하지 않는다.
- 측면 챔피언을 라이브러리 부품으로 자동 분해하지 않는다.
- 어느 축도 개선되지 않을 때 종료 후보라는 사실은 계산 가능하지만,
  종료 승인·메타게임 `deprecated` 상태는 아직 구현하지 않았다.
- 다음 전체 배관 후보는 종료·잠정 챔피언 스냅샷과 메타게임 상태 전이 골격이다.

## v0.8.0 — 지연 재사용 라이브러리 + 목적 주석 승인

작성일: 2026-06-22  
기준 설계서: §11, §13-1 `salvageable_part`

### 목적

후보 전체가 탈락해도 보존할 수 있는 독립 부품을 메타와 함께 저장하고,
목적 주석을 별도 승인한 뒤 목적→전제·조건 순서로 조회한다.

### 추가

- `LibraryLedger`
- `LibraryPart`
- `PurposeApprovalEvent`
- `LibraryMatch`
- 필수 보관 메타
  - 성립 전제
  - 검증 맥락
  - `works_when`
  - `fails_when`
  - 목적 주석
  - 검증 상태
  - 원 event·candidate 출처
- 검증 상태
  - `preserved_verified`
  - `salvaged_unverified`
- 목적 상태
  - `proposed_unapproved`
  - `approved`
- CLI
  - `list-library-intake`
  - `add-library-part`
  - `approve-library-purpose`
  - `query-library`
- 이벤트
  - `library_intake_candidate_recorded`
  - `library_part_proposed`
  - `library_purpose_approved`

### 재심 연결

외부 재심 결과에 `salvageable_part`가 있으면 즉시 정식 부품으로 만들지 않는다.

```text
appeal_result
→ library_intake_candidate_recorded
→ metadata_status: incomplete
→ purpose_status: missing
→ searchable: false
```

전제·조건·목적·검증 상태를 사람이 채운 뒤에만 정식 부품으로 제안할 수 있다.

### 조회 규칙

1. 승인된 목적 주석이 정확히 일치하는가
2. 그 부품의 전제·`works_when`이 요청 조건을 포함하는가

의미 유사도 점수나 임계값은 만들지 않았다. 현재는 공백·대소문자를 정규화한
정확 일치만 사용한다.

### 안전 조건

- 목적 승인 전 검색 금지
- 출처 event가 존재하지 않으면 저장 금지
- 필수 메타가 빠지면 저장 금지
- 목적 주석 중복 승인 금지
- 미검증 회수 부품을 검증된 상태로 자동 승격하지 않음
- 조회 결과를 자동 합성하거나 출고하지 않음

### 회귀·통수 검증

- 변경 전 기준선: 35/35 통과
- 변경 후 전체: 43/43 통과
- 명시적 회귀 계약: 6/6 통과
- 격리 Python 캐시에서 `compileall` 통과
- 재심 회수 부품이 미완성 intake로만 들어오는지 확인
- 승인 전 조회 0건
- 목적 승인 후 동일 목적·조건 조회 1건
- 목적 불일치 시 조건을 보지 않고 제외
- 조건 불일치 제외
- `salvaged_unverified` 상태 보존 확인

### 현재 경계

- 라이브러리 부품을 새 후보에 자동 합성하지 않는다.
- 목적의 의미 유사도 검색은 구현하지 않는다.
- 합성물 재심사 경로는 일반 `run`을 재사용할 예정이며 별도 우회로를 만들지 않는다.
- 다음 전체 배관 후보는 사전식 래칫과 측면별 챔피언 저장 골격이다.

## v0.7.0 — Gate 1→3 상태 전이 골격 + 정식 회귀검증

작성일: 2026-06-22  
기준 설계서: §10-1, §17, §19, §24

### 목적

세부 Rubric을 확정하지 않은 상태에서 Gate 1→2→3의 이동 배관과 revise 회송,
최종 종료 상태를 먼저 연결한다.

### Gate 상태

- `awaiting_review`
- `awaiting_revision`
- `awaiting_human_review`
- `terminated_rejected`
- `completed_accepted`

### 허용 이동

- Gate 1·2
  - `pass_to_next_gate`
  - `revise`
  - `reject`
- Gate 3
  - `accepted_synthesis`
  - `needs_human_review`
  - `revise`
  - `reject`
- Gate 3 사람 검토 후
  - `accepted_synthesis`
  - `revise`
  - `reject`

### 추가

- `GateLedger`
- `GateFlowState`
- `GateDecisionEvent`
- `GateRevisionEvent`
- 일반 실행의 `review_batch_completed` 이후 `gate_flow_started`
- CLI 출력의 `gate_flow`
- CLI
  - `show-gate`
  - `record-gate-decision`
  - `submit-gate-revision`
- 이벤트
  - `gate_flow_started`
  - `gate_decision_recorded`
  - `gate_revision_submitted`

### 설계 경계

- ReviewBatch는 Gate 입력 출처로 연결되지만 결정을 자동 생성하지 않는다.
- Hard Gate·절대 점수·단계별 threshold는 아직 구현하지 않는다.
- 판정은 사람 또는 향후 Rubric Adapter가 명시적 사건으로 기록해야 한다.
- 궤변생성기는 내부 침투 테스트이므로 Gate flow를 시작하지 않는다.

### 회귀검증 정식화

이전에도 매 변경마다 전체 테스트를 다시 실행했다. v0.7.0부터 이를 파일과
계약으로 명시한다.

- `tests/test_regression.py`
  - 생성→심사→Gate 시작 순서
  - 궤변 사건 기본 shadow
  - 미승인 부정예시 목록 비어 있음
  - Appeal packet 없는 결과 재입력 차단
  - 모든 신규 이벤트 ID 보존
- 변경 전 기존 기준선: 24/24 통과
- 변경 후 전체: 35/35 통과
- 명시적 회귀 계약: 5/5 통과

### 통수 시험

실제 CLI로 다음 흐름을 확인했다.

```text
Gate 1 awaiting_review
→ Gate 2 awaiting_review
→ Gate 3 awaiting_review
→ completed_accepted
```

- 격리 Python 캐시에서 `compileall` 통과
- 잘못된 단계 판정 차단
- 종료 상태 재이동 차단
- revise 없이 수정본 제출 차단
- revise 후 같은 단계로 복귀 및 candidate 교체 확인
- Gate 3 사람 검토 후 후속 판정 확인

### 다음 후보

전체 골격 우선 원칙상 다음은 지연 재사용 라이브러리와 목적 주석의 저장·조회
배관이다. Gate Rubric의 정밀 구현은 실제 흐름 완공 이후 사례를 보며 채운다.

## v0.6.0 — 외부 Claude 재심 문서 배관

작성일: 2026-06-22  
기준 설계서: §13-1, 부록 C

### 목적

내부 심사 결과가 비거나 충돌하는 경우, 자동 API 호출 없이 외부 Claude 채팅으로
전달할 재심 문서를 출력하고 그 2차 의견을 사건 원장에 재입력한다.

### 자동 문서 트리거

- `reviewer_conflict`
- `empty_aspect`
- `needs_human_review`
- `dependent_core_boundary`
  - 종속핵심 심사가 명확한 reject가 아니라 `revise` 경계일 때만

명확한 reject를 무조건 외부 재심으로 보내지 않는다.

### 추가

- `AppealService`
- `AppealPacket`
- `AppealResultEvent`
- Markdown 재심 문서 자동 출력
  - 기본 위치: 이벤트 로그 옆 `appeals/`
- 문서 내용
  - 메타·트리거
  - 원 과제와 제약
  - 후보 전문
  - 1차 심사 결과
  - 하드체크 자리
  - 의심 지점
  - 구체 재심 질문
  - YAML 출력 계약
- CLI 출력에 `appeal_packet`과 문서 절대 경로 표시
- CLI `record-appeal-result`
- 이벤트
  - `appeal_packet_created`
  - `appeal_document_written`
  - `appeal_trigger_connected`
  - `appeal_result_recorded`

### 재입력 판정

- `uphold`
- `overturn`
- `uncertain`

`overturn`에는 `type | where | why` 결함이 하나 이상 필요하다.

### 설계 충돌 해소

설계서의 예시 출력에는 외부 Claude가 결함 확정을 표시하는 Boolean 필드가 있지만,
동일 절은 Claude가 2차 의견일 뿐 최종 영점이 아니라고 규정한다.

구현은 후자를 우선한다.

- 외부 결과는 확정 사건이 아님
- `overturn`·`uncertain`은 사람·도구 확인 필요로 기록
- `confirm-case` 상태 전이를 자동 호출하지 않음
- 부정예시 활성과 심사 규칙 패치를 자동 호출하지 않음

### 검증

- 자동 테스트: 24/24 통과
- 격리 Python 캐시에서 `compileall` 통과
- 정상 `clear` 후보에서 문서 미생성
- 동일 측면 충돌에서 문서 자동 생성
- 문서에 외부 재심 역할과 확인 필요 계약 포함
- `overturn` 재입력 후 자동 case 확정 없음
- `overturn` 재입력 후 자동 부정예시 활성 없음
- 동일 Appeal 결과 중복 입력 차단
- CLI 필수 인자 확인

### 현재 경계

- 실제 Claude 호출은 사용자가 구독 채팅에서 수동 수행한다.
- 하드체크 결과는 아직 빈 자리다.
- 당시 재심의 `salvageable_part`는 사건에만 보관됐다.
  외부 재심 입고는 v0.6.0, 내부 Review 입고는 v0.10.8에서 연결됐다.
- 재심 `feedback_to_thesis`도 사건에 보관되지만 사람·도구 case 확인 전에는
  부정예시 활성 후보가 아니다.

## v0.5.0 — 명시적 되먹임 승인 + Block-rule 주입 Adapter

작성일: 2026-06-22  
기준 배관 구간: `confirmed case → readiness approval → activation approval → thesis context`

### 맥락 확인

현재 작업은 “전체 배관 골격을 먼저 만들고 구간마다 소량 통수 시험” 원칙과
일치한다.

설계서 §12의 보정 선행조건은 별도 비율·점수 계기판으로 구현하지 않았다.
대신 사람 또는 도구가 근거를 첨부하는 **되먹임 준비 승인 사건**으로 구현했다.

### 추가

- `FeedbackReadinessEvent`
  - 준비 승인 ID
  - 사람/도구 주체
  - 적용 범위
  - 근거와 이유
- `NegativeExampleActivationEvent`
  - confirmed case ID
  - 준비 승인 ID
  - 원 case report event ID
  - Block-rule
  - 승인 주체와 이유
- `NegativeExampleRule`
  - 생성 프롬프트에 전달되는 최소 자료형
- `CaseLedger.record_feedback_readiness()`
- `CaseLedger.approve_negative_example()`
- `CaseLedger.active_negative_examples()`
- 정 생성 Prompt의 Block-rule 주입 구역
- CLI
  - `approve-feedback-readiness`
  - `approve-negative-example`
- 이벤트
  - `feedback_readiness_approved`
  - `negative_example_activation_approved`
  - `negative_example_context_applied`

### 밸브 조건

```text
confirmed
  + feedback_readiness_approved
  + case별 negative_example_activation_approved
  → active_approved
  → 정 생성 프롬프트 Block-rule 전달
```

### 역류·오배관 차단

- confirmed만으로 주입 불가
- 준비 승인 ID가 없거나 존재하지 않으면 활성 불가
- unconfirmed·dismissed case 활성 불가
- 동일 case 중복 활성 불가
- 활성 사건의 원 case event ID 불일치 차단
- 활성 사건이 참조하는 준비 승인 event 재검증
- 생성 시 사용한 case ID를 별도 이벤트로 기록

### 검증

- 자동 테스트: 21/21 통과
- 격리 Python 캐시에서 `compileall` 통과
- confirmed 후 미승인 상태에서 생성 Context가 비어 있음
- 준비 승인 없는 활성 시도 차단
- 명시 승인 후 Block-rule 1건 전달 확인
- 중복 활성 승인 차단
- 주입 case ID 추적 이벤트 확인

### 현재 경계

- 준비 승인은 성능 측정기가 아니라 근거가 붙은 운영 승인 사건이다.
- Block-rule만 주입하며 원 궤변 전문은 생성 프롬프트에 넣지 않는다.
- 활성 규칙의 검색·도메인별 선택·가시성 단계는 아직 없다.
- Gate 1→3와 외부 재심 배관도 아직 연결되지 않았다.

## v0.4.0 — 케이스 확인 원장 + 부정예시 활성 후보 밸브

작성일: 2026-06-22  
기준 배관 구간: `filter_escape_candidate → confirmation → negative-example eligibility`

### 목적

필터 통과 결함 의심 사건을 사람 또는 도구가 확인하고, 확정 사건만 부정예시
활성 후보로 승격하되 실제 생성기 주입은 계속 차단한다.

### 추가

- `CaseLedger`
  - 기존 JSONL 이벤트 로그를 append-only 사건 원장으로 사용
  - case report와 후속 확인 사건을 재구성
  - 현재 상태 조회
- 모든 신규 이벤트에 고유 `event_id`
- `CaseConfirmationEvent`
  - 이전·신규 상태
  - 확인 주체 유형과 식별자
  - 증거
  - 판단 이유
  - 원 case report event ID
- `CaseState`
  - 원 case report
  - 확인 사건 이력
  - 현재 확인 상태
  - 현재 부정예시 상태
- CLI
  - `show-case`
  - `confirm-case`

### 상태 전이

```text
unconfirmed → confirmed
unconfirmed → dismissed
```

- `confirmed` → `eligible_pending_approval`
- `dismissed` → `ineligible_dismissed`
- 두 상태 모두 `negative_example_activated: false`

### 차단 규칙

- `confirmed` 또는 `dismissed` 종료 상태를 다시 변경할 수 없음
- 근거·이유·확인 주체 없는 상태 전이 금지
- `caught_by_filter` 사건을 필터 통과 결함 확정 사건으로 승격 금지
- 기존 report 수정 금지
- 부정예시 자동 활성화 금지

### 이벤트

- `case_confirmation_recorded`
- `negative_example_activation_candidate_recorded`

두 이벤트는 원 case report의 `event_id`를 출처로 보존한다.

### 검증

- 자동 테스트: 16/16 통과
- 격리 Python 캐시에서 `compileall` 통과
- 필터 통과 후보의 `confirmed` 전이 성공
- 확정 후에도 부정예시 활성화 `false` 확인
- `dismissed` 후 재전이 차단 확인
- 필터 적발 사건의 잘못된 확정 승격 차단 확인
- 모든 신규 이벤트의 `event_id` 확인
- CLI 도움말과 필수 인자 확인

### 현재 경계

- 사건 원장이 부정예시 저장소의 초기 골격 역할을 한다.
- 확정 사건은 활성 후보일 뿐 실제 프롬프트에 주입되지 않는다.
- 다음 구간에서 활성 승인·주입 Adapter(연결부)의 자리만 만들 수 있다.
- 되먹임 준비 승인과 실제 품질 검토 전에는 기본 밸브를 닫힌 상태로 유지한다.

## v0.3.0 — 궤변생성기 자리 + 역할별 모델 Pipeline

작성일: 2026-06-22  
기준 설계서: §12, §13, §26~28

### 결정

Gate 1보다 궤변생성기 자리와 역할별 모델 Pipeline을 먼저 구현했다.

이유:

- 현재 표본으로 Gate 규칙을 먼저 고정하면 임의성이 크다.
- 궤변생성기는 현재 심사관이 실제로 무엇을 놓치는지 사건 원본을 만든다.
- Gate 1은 이후 축적된 필터 통과 결함 케이스를 입력으로 독립 구현할 수 있다.
- 단, 심사 통과만으로 결함 확정이나 부정예시 활성화를 하지 않는다.

### 용어 변경

비율을 전제하는 기존 명칭을 프로젝트 용어에서 제거했다.

정식 용어:

**필터 통과 결함 케이스 보고(Filter-escape case report)**  
= 심사 필터를 통과한 결함 의심·확정 사건의 원본 기록.

상태:

- `caught_by_filter`
- `filter_escape_candidate`
- `unconfirmed`
- `confirmed`
- `dismissed`

별도 비율·분모·임계값·Dashboard는 구현하지 않는다.

### 추가

- `AdversaryEngine`
  - 현재 심사관 역할과 검사 규칙을 궤변생성기에 노출
  - 내부 침투 테스트 후보 생성
  - 동일 Reviewer Orchestrator로 순차 심사
  - 필터 적발/통과 의심 케이스 분리
- `FilterEscapeCaseReport`
  - 후보 원문
  - 심사 결과 전체
  - 케이스 상태
  - 확인 상태
  - 부정예시 상태와 활성 여부
- 부정예시 안전 상태
  - `shadow_unconfirmed`
  - `negative_example_activated: false`
- `RoleModelPipeline`
  - 정 생성 backend
  - 궤변 생성 backend
  - 기본 심사 backend
  - 심사관별 전용 backend
- CLI 모델 라우팅
  - `--thesis-model`
  - `--adversary-model`
  - `--reviewer-model REVIEWER_ID=MODEL`
- 설계서의 로컬 역할 자리
  - 정 생성기
  - 논리 심사관
  - 구조·범위 심사관
  - 코드 심사관
  - 수학 심사관
  - 물리 심사관
  - 빈 측면 심사관
- `adversary` CLI 명령
- 이벤트
  - `adversary_task_created`
  - `filter_escape_case_reported`
  - `negative_example_case_shadowed`

외부 Claude는 설계서대로 자동 Pipeline에 넣지 않는다.

### 부정예시 되먹임 경계

- 현재는 저장 경로만 구축했다.
- 미확정 케이스는 생성기에 주입하지 않는다.
- 활성 주입은 calibration 및 사용자·도구 확정 경로 구현 후 별도 단계에서 연다.

### 검증

- 자동 테스트: 13/13 통과
- 격리된 Python 캐시 경로에서 `compileall` 통과
- 필터 적발 궤변이 `caught_by_filter`로 기록됨
- 필터 통과 결과가 확정이 아닌 `filter_escape_candidate`로 기록됨
- 두 경우 모두 부정예시 자동 활성화가 꺼져 있음
- 심사관별 전용 backend 라우팅 검증
- Mock adversary end-to-end 실행 성공
- 실제 Ollama 역할 분리 실행 성공
  - 궤변 생성: `qwen2.5-coder:1.5b`
  - 논리 심사: `qwen3:14b`
  - 논리 심사관이 성급한 일반화를 적발
  - `caught_by_filter`, `shadow_unconfirmed`, 활성화 `false`

관측:

- 1.5B 궤변 생성물은 반복이 많고 결함이 노출되어 쉽게 적발됐다.
- 이는 Pipeline 연결 성공과 별개로 공격 모델의 생성 품질이 충분하지 않다는
  단일 실행 관측이다. 모델 변경이나 성능 비율 결론으로 일반화하지 않는다.

### 다음 후보 — 아직 구현하지 않음

필터 통과 결함 케이스의 사람·도구 확인 흐름:

- `unconfirmed → confirmed | dismissed`
- confirmed 케이스만 부정예시 활성 후보로 승격
- 심사관 규칙 패치 제안 생성
- 실제 생성기 문맥 주입은 별도 승인 후 활성화

## v0.2.0 — Reviewer Orchestrator

작성일: 2026-06-22  
기준 설계서: §7 다측면 자가선별 심사, §9 독립/종속 측면, §13 빈 측면·충돌

### 목적

단일 논리 심사관이 pipeline에 고정된 구조를 제거하고, 여러 심사관을 등록 순서대로
실행하면서 관할과 판정을 표준 방식으로 수집하는 공통 계층을 만든다.

### 추가

- `ReviewerRegistry`
  - 심사관 등록 순서 보존
  - reviewer ID 중복 차단
  - 전체 또는 선택 실행
- 기본 심사관 2명
  - `logic_reviewer`
    - 측면: `logic`
    - 유형: `dependent_core`
  - `scope_reviewer`
    - 측면: `scope`
    - 유형: `independent`
- `ReviewerOrchestrator`
  - 심사관을 등록 순서대로 순차 실행
  - 각 심사관의 관할 자가선별
  - 관할을 주장한 심사관만 본심 실행
  - 결과를 공통 `ReviewBatch`로 취합
- 관할 출력 JSON Schema
  - `applicable`
  - `reasoning`
  - `confidence`
- 다측면 심사 결과 메타데이터
  - reviewer
  - aspect
  - dependency
- Orchestrator 상태
  - `clear`
  - `objections`
  - `dependent_core_blocked`
  - `conflict`
  - `empty_aspect`
  - `human_review`
- 필수 측면 지정 CLI
  - `--required-aspect`
- 실행 심사관 선택 CLI
  - `--reviewer`
- Shadow 부정예시에 reviewer와 aspect 기록

### 설계 경계

- Orchestrator는 심사 결과를 취합하지만 Gate 합격·불합격은 결정하지 않는다.
- 출력의 `gate_decision`은 명시적으로 `null`이다.
- `dependent_core_blocked`는 종속핵심 반대 판정이 존재한다는 신호이며,
  아직 §10·§17~20의 전체 Gate 규칙을 적용한 최종 불합격 판정이 아니다.
- 빈 측면은 사용자가 `required_aspects`로 요구한 측면에만 판정한다.
  모든 비관할 측면을 자동으로 결함 취급하지 않는다.

### 검증

- Python 단위 테스트: 10/10 통과
- Python `compileall`: 통과
- Mock 다중 심사:
  - logic→scope 등록 순서 실행 확인
  - 관할 판정 후 본심 실행 확인
  - 필수 측면 충족 확인
- 빈 측면 탐지 테스트: 통과
- 동일 측면 판정 충돌 테스트: 통과
- 종속핵심 차단과 Gate 결정 분리 테스트: 통과
- `qwen3:14b` 실제 Ollama:
  - 논리 관할 자가선별 성공
  - 인과 오류 미끼 적발
  - `dependent_core_blocked` 상태 생성
  - `gate_decision: null` 유지

### 변경

- `Harness.run()` 반환값이 단일 `Review`에서 `ReviewBatch`로 변경됐다.
- 이벤트 로그의 단일 `candidate_reviewed`를 `review_batch_completed`로 교체했다.
- Probe 결과가 단일 review 대신 전체 review batch와 적발 심사관 목록을 보관한다.
- 패키지 버전을 `0.2.0`으로 올렸다.

### 현재 한계

- 기본 심사관 2명은 같은 backend와 같은 모델을 공유할 수 있다.
  역할 분리는 구현됐지만 cross-lineage(다른 학습 계통) 독립성은 아직 없다.
- scope 심사관은 전체 설계서 루브릭의 최소 축소판이다.
- 동일 측면 충돌은 탐지만 하며 외부 재심 문서를 자동 생성하지 않는다.
- 관할 자가선별 자체가 틀릴 수 있으므로 required aspect와 미끼 검증이 필요하다.

### 다음 후보 — 아직 구현하지 않음

Gate 1 공통 계약의 최소 구현:

- §18 공통 Hard Gate 결과 구조
- `reject/revise/pass_to_next_gate`의 Gate 1 상태 전이
- 심사관별 결과를 Gate 입력으로 변환
- 종속핵심 차단 규칙
- `gate_decision` 생성

이 단계가 다음 후보인 이유는 다측면 결과를 받을 조정계층이 생겨 이제 Gate 규칙을
특정 모델이나 심사관에 종속시키지 않고 별도 계층으로 구현할 수 있기 때문이다.

## v0.1.0 — 최소 수직 슬라이스

작성일: 2026-06-22  
기준 설계서: `유추 생성 · 다측면 심사 하네스 — 통합 설계서 v1.3`

### 목적

전체 심사단을 구현하기 전에 다음 end-to-end(처음부터 끝까지) 배관이 실제
환경에서 작동하는지 확인한다.

```text
과제 입력 → 정(thesis) 생성 → 논리 반(anti) 심사 → 판정 → JSONL 로그
                                  ↑
                         known-flaw probe
```

이 릴리스는 완성 제품이 아니라 이후 기능을 연결할 수 있는 실행 기준선이다.

### 추가

- Python 표준 라이브러리만 사용하는 CLI(Command-Line Interface·명령줄 프로그램)
- `mock` backend
  - 모델 없이 결정론적으로 전체 흐름 검증
  - 기본 미끼 3종 판정
- `ollama` backend
  - 로컬 `/api/generate` 호출
  - 생성과 심사 역할 분리
  - 모델명과 서버 주소 교체 가능
- 정 생성 프롬프트
  - 핵심 제안
  - 작동 원리
  - 적용 조건
  - 실패 조건
  - 검증 방법
- 논리 심사 프롬프트
  - 전제–결론 연결
  - 상관관계와 인과관계 혼동
  - 순환논증
  - 숨은 전제
  - 과잉 일반화
  - 반례와 적용 범위
- 심사 결과 자료형과 검증
  - `reject`
  - `revise`
  - `pass_to_next_gate`
  - `needs_human_review`
- Ollama 요청의 JSON Schema(JSON 구조 계약)
  - 필수 필드 누락 방지
  - 판정값 제한
  - confidence 범위 제한
- known-flaw probe(알려진 결함 미끼) 3종
  - 상관관계의 인과 오인
  - 순환논증
  - 성급한 일반화
- append-only JSONL 이벤트 로그
  - 과제 생성
  - 후보 생성
  - 후보 심사
  - 미끼 심사
  - 부정예시 shadow 기록
- 패키지 실행 진입점과 기본 문서
- `.gitignore`

### 구현 중 발견하여 수정

- Ollama `format: "json"`만 사용하면 유효하지만 비어 있는 `{}` 응답도 허용되는
  문제를 확인했다.
- 단순 JSON 모드를 필수 속성이 정의된 JSON Schema로 교체했다.
- Qwen3가 confidence를 0~1 척도로 해석할 수 있어 0~100 정수 백분율이라고
  프롬프트에 명시했다.

### 검증

- Python 단위 테스트: 5/5 통과
- Python `compileall`: 통과
- mock 미끼: 3/3 적발
- `qwen3:14b` 실제 미끼:
  - 상관관계의 인과 오인 적발
  - `reject` 판정
  - 구조화 출력 계약 충족
- `qwen3:14b` 실제 end-to-end 실행:
  - 후보 생성 성공
  - 논리 심사 성공
  - `pass_to_next_gate` 판정
  - 이벤트 로그 기록 성공

### 현재 구현 경계

완료:

- 단일 과제의 생성→심사→판정→로그 배관
- 단일 논리 심사관
- 미끼 투입과 적발 여부 기록
- 부정예시의 shadow 기록
- backend 교체 경계

부분 구현:

- 설계서 §12 부정예시 되먹임
  - 기록만 구현
  - 생성 프롬프트 재주입은 calibration 전이므로 비활성
- 설계서 §13 메타검증
  - known-flaw probe만 구현
  - adversary와 블라인드 재투입은 미구현
- 설계서 §17 판정 체계
  - 최소 판정값만 구현
  - `accepted_synthesis`와 3단계 상태 전이는 미구현
- 설계서 §21~22 프롬프트·출력 규격
  - 논리 심사에 필요한 축소 schema만 구현
  - 전체 Hard Gate·점수는 미구현
  - salvage 필드는 v0.10.8에서 구현

미구현:

- 다측면 심사관 자가선별과 순차 전수 실행
- 7개 로컬 계통 + 외부 Claude 재심 구성
- 도메인별 독립/종속 측면 합산
- 공통 Hard Gate와 도메인별 전체 루브릭
- Gate 1→2→3 상태 전이와 revise 루프
- 사전식 래칫과 측면별 챔피언
- 지연 재사용 라이브러리와 목적 주석 검증
- calibration 판정과 부정예시 활성화
- 블라인드 재투입과 필터 통과 결함 케이스 확정
- Appeal Request Packet 생성·재입력
- 궤변생성기와 4단계 적대적 진화 루프
- 하드체크 연동(SymPy, 컴파일러, 테스트 러너, 차원검산)
- 종료 판정과 메타게임 적응
- Kill-switch 자동 평가
- IPEX-LLM 또는 대체 가속 backend

### 알려진 제약

- 현재 보유 모델이 모두 Qwen 계통이므로 cross-lineage(다른 학습 계통) 독립성은
  검증하지 않았다.
- 같은 `qwen3:14b`가 생성기와 심사관 역할을 모두 맡을 수 있어 공통 맹점이
  그대로 남는다.
- 미끼 3건은 배관 검증용이다. 일반적인 필터 성능 비율을 추정할 표본이 아니다.
- confidence는 로그용이며 현재 판정이나 게이트에 사용하지 않는다.
- 현재 `pass_to_next_gate`는 “논리 심사관 하나를 통과했다”는 뜻일 뿐,
  설계서의 Gate 1 전체 통과를 뜻하지 않는다.

### 다음 예정 — 아직 구현하지 않음

`Reviewer Orchestrator(심사관 조정계층)`:

1. 심사관 registry(등록부)
2. 관할 자가선별
3. 심사관 순차 실행
4. 심사 결과의 공통 schema 정규화
5. 빈 측면·판정 충돌 탐지
6. 독립 측면과 종속핵심 결과 분리

선정 이유:

- 현재 단일 심사관 하드코딩이 가장 큰 구조적 병목이다.
- 3단계 게이트, 재심, 필터 통과 결함 케이스 분석, 다계통 모델 추가가 모두 여러 심사 결과를
  표준 방식으로 수집하는 기능에 의존한다.
- 모델부터 추가하면 심사관별 호출·출력·오류 처리가 pipeline에 중복되어 이후
  구조 변경 비용이 커진다.
- 이 계층을 먼저 만들면 새 모델과 새 루브릭은 설정 추가로 확장할 수 있다.
