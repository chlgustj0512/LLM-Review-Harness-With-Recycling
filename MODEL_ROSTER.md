# 확정 모델 명단

기준일: 2026-06-23  
실행 프로필: `confirmed-local`

이 문서에서 “확정”은 공식 Ollama 식별자가 존재하고 현재 장비의 약 18 GiB
iGPU 가용 메모리 안에서 단일 모델 순차 실행이 가능한 크기라는 뜻이다.
아직 설치하지 않은 모델까지 실운전이 끝났다는 뜻은 아니다.

## 7+1 구성

| 자리 | Harness 역할 | 확정 식별자 | Ollama 크기 | 현재 상태 |
|---|---|---:|---:|---|
| 1 | 정(thesis) 생성기 | `qwen3.5:9b` | 6.6 GB | 설치·구조화 출력·iGPU 실행 확인 |
| 2 | 코드 심사 | `gemma4:12b` | 7.6 GB | 설치·구조화 출력·iGPU·양방향 심사 확인 |
| 3 | 논리 심사 | `phi4-reasoning:14b` | 11 GB | 설치·구조화 출력·iGPU·미끼 적발 확인 |
| 4 | 수학 심사 | `gpt-oss:20b` | 13 GB | 설치·구조화 fallback·iGPU·양방향 심사 확인 |
| 5 | 물리 심사 | `llama3.1:8b` | 4.9 GB | 조건부 실배치: iGPU·정상/결함 판정 확인, 설명 일관성 주의 |
| 6 | 범위·구조 심사 | `ministral-3:14b` | 9.1 GB | 설치·iGPU·정상/범위과장 양방향 심사 확인 |
| 7 | 사각지대 심사 | `qwen3.5:9b` | 6.6 GB | 설치·iGPU·정상/개인정보 누락 양방향 심사 확인 |
| 보강 | 비차단 사후 감사 | `olmo2:13b` | 8.4 GB | 11 GB 실행·100% GPU·영어 정상/결함 양방향 확인 |
| 도구 | 감사 경계 번역 | `qwen3.5:9b` | 6.6 GB | 한↔영 핵심 조건 보존·한국어 보고서 생성 확인 |
| +1 | 외부 재심 | Claude Opus 4.8 / `claude-opus-4-8` | 외부 | 수동 문서 재심 |

논증 결함 테스트케이스 생성기는 독립 심사표의 구성원이 아니라 필터 검증용
보조 역할이다. 현재 설치된 `qwen2.5-coder:14b`를 배정한다. 외부 시스템 공격을
생성하지 않으며 후보와 숨은 정답표를 분리한다.

## 잘못되거나 운용상 부적합했던 이름

| 기존 표기 | 판정 | 교체 |
|---|---|---|
| `Qwen 3.6-A3B` | 정확한 Ollama 태그가 아니다. Qwen3.6 공식 목록은 `27b`, `35b`이며 각각 17 GB, 24 GB다. | `qwen3.5:9b` |
| `Gemma 4 12B` | 모델명은 존재하지만 실행 태그 표기가 빠졌다. | `gemma4:12b` |
| `Phi-4 Reasoning 14B` | 설명명만 적혀 있었다. | `phi4-reasoning:14b` |
| `GPT-OSS 20B` | 대소문자 설명명만 적혀 있었다. | `gpt-oss:20b` |
| `Llama 3.3 8B` | 존재하지 않는다. Llama 3.3은 70B만 제공되며 43 GB다. | `llama3.1:8b` |
| `Llama 4 Scout` | 존재하지만 Ollama 패키지가 67 GB라 현재 장비에 부적합하다. | `llama3.1:8b` |
| `Mistral Small 4 24B` | 해당 정확 모델명이 없다. | `ministral-3:14b` |
| `GLM available min` | 재현 가능한 정확 태그가 아니었다. `glm4:9b`를 실제 시험했으나 정상안을 3회 연속 오탐했다. | 사각지대 역할은 `qwen3.5:9b` |

최신 모델이라는 이유만으로 채택하지 않았다. 예를 들어
`glm-4.7-flash:q4_K_M`은 19 GB라 현재 iGPU 가용량 약 18 GiB를 넘고,
`qwen3.6:27b`는 모델 자체가 17 GB여서 KV cache(문맥 기억 공간)와 실행
buffer(작업 공간)를 더하면 full offload(전량 GPU 적재) 여유가 거의 없다.

## 실행

명단을 코드에서 직접 적용:

```powershell
python -m harness run `
  --backend ollama `
  --model-profile confirmed-local `
  --reviewer logic_reviewer `
  --required-aspect logic `
  --task "검토할 과제"
```

개별 역할을 임시 교체하면 명시 인자가 프로필보다 우선한다.

```powershell
python -m harness run `
  --backend ollama `
  --model-profile confirmed-local `
  --reviewer-model logic_reviewer=qwen3:14b `
  --task "검토할 과제"
```

프로필은 모델을 자동 다운로드하지 않는다. 현재 `qwen3.5:9b`,
`gemma4:12b`, `phi4-reasoning:14b`, `gpt-oss:20b`는 실운전 확인을 마쳤다.
`llama3.1:8b`는 연결과 양방향 판정은 확인했지만 설명 일관성 문제로 조건부
실배치다. `ministral-3:14b`는 설치·full offload·정상 통과·범위과장 적발까지
확인했다. 사각지대 역할은 `qwen3.5:9b`가 관할 정상안 통과와 개인정보·동의·
접근통제 누락 적발을 모두 통과했다. `glm4:9b`도 설치와 100% GPU 적재에는
성공했지만 명시적 비수집 정상안을 반복 거부해 운영 프로필에서 제외했다.
`olmo2:13b`는 Gate 심사관이 아니라 비차단 Post-review Auditor(사후 감사관)로
배치한다. 한국어 후보는 그대로 유지하고 영어 정규화본만 감사한다.

## 공식 식별자 근거

- 🟢T1 [Ollama GPU/Vulkan 지원](https://docs.ollama.com/gpu)
- 🟢T1 [qwen3.5:9b](https://ollama.com/library/qwen3.5:9b)
- 🟢T1 [gemma4:12b](https://ollama.com/library/gemma4:12b)
- 🟢T1 [phi4-reasoning:14b](https://ollama.com/library/phi4-reasoning:14b)
- 🟢T1 [gpt-oss:20b](https://ollama.com/library/gpt-oss:20b)
- 🟢T1 [llama3.1:8b](https://ollama.com/library/llama3.1:8b)
- 🟢T1 [ministral-3:14b](https://ollama.com/library/ministral-3:14b)
- 🟢T1 [glm4:9b](https://ollama.com/library/glm4:9b)
- 🟢T1 [olmo2:13b](https://ollama.com/library/olmo2:13b)
- 🟢T1 [Qwen3.6 태그 목록](https://ollama.com/library/qwen3.6)
- 🟢T1 [Llama 3.3 태그 목록](https://ollama.com/library/llama3.3)
- 🟢T1 [Llama 4 태그 목록](https://ollama.com/library/llama4)
- 🟢T1 [Anthropic Claude Opus 4.8 발표](https://www.anthropic.com/news/claude-opus-4-8)

[사각지대 정상안 오탐이 재발하거나 정 생성기와 동일 모델을 써서 생기는
동일계통 blind spot(공통 사각지대)이 실제 사건에서 확인되면, 별도 계통 모델을
다시 선발한다.]
