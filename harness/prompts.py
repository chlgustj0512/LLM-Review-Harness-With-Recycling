from __future__ import annotations

from harness.models import NegativeExampleRule, ReviewerSpec, Task


def thesis_prompt(
    task: Task,
    negative_examples: list[NegativeExampleRule] | None = None,
) -> str:
    constraints = "\n".join(f"- {item}" for item in task.constraints) or "- 없음"
    rules = negative_examples or []
    block_rules = (
        "\n".join(
            f"- [{rule.case_id}] {rule.block_rule}"
            for rule in rules
        )
        if rules
        else "- 활성 규칙 없음"
    )
    return f"""당신은 정(thesis) 생성기다.

목표:
{task.goal}

제약:
{constraints}

확정·승인된 부정예시 Block-rule:
{block_rules}

목표에 직접 기여하는 후보 하나를 작성하라.
반드시 다음을 포함하라:
1. 핵심 제안
2. 작동 원리
3. 적용 조건
4. 실패 조건
5. 검증 방법

Block-rule이 있으면 해당 실패 패턴을 피하라.
간결하지만 독립적으로 심사 가능한 완결된 한국어 텍스트만 출력하라."""


def jurisdiction_prompt(
    task: Task,
    candidate_text: str,
    reviewer: ReviewerSpec,
) -> str:
    return f"""당신은 {reviewer.reviewer_id}다.
담당 측면은 {reviewer.aspect}이며 역할은 다음과 같다:
{reviewer.description}
구체 검사 지시:
{reviewer.instructions}

원 과제:
{task.goal}

후보:
---
{candidate_text}
---

이 후보에 담당 측면이 실질적으로 존재하여 심사할 관할이 있는지 판단하라.
단지 익숙한 주제라는 이유로 관할을 주장하지 마라.
관할은 결함 발견 여부가 아니라 검사 대상의 존재 여부다.
후보에 담당 측면의 법칙·수식·주장·조건·단위·실행물이 실제로 들어 있으면,
아직 결함이 없어 보이거나 결함 여부를 판단하지 않았더라도 applicable=true다.
담당 측면에서 요구되는 적용 조건·예외·실패 조건·검증 요소가 빠져 있는 것
자체도 그 측면의 검사 대상이므로, 누락을 이유로 applicable=false라 하지 마라.
결함의 유무와 판정은 다음 Review 단계에서 처리하라.
관할이 없으면 applicable=false로 빠져라.

JSON 객체 하나만 출력하라. Markdown code fence는 쓰지 마라.
필수 schema:
{{
  "applicable": true,
  "reasoning": "관할 판단 근거",
  "confidence": 0
}}

confidence는 0~100 정수 백분율이다."""


def review_prompt(
    task: Task,
    candidate_text: str,
    reviewer: ReviewerSpec,
) -> str:
    constraints = "\n".join(f"- {item}" for item in task.constraints) or "- 없음"
    return f"""당신은 {reviewer.reviewer_id}다.
담당 측면: {reviewer.aspect}
역할: {reviewer.description}
구체 검사 지시:
{reviewer.instructions}

칭찬이나 문체 평가가 아니라 담당 측면의 결함을 단서 없이 검사하라.
담당 측면 밖의 판정은 하지 마라.

원 과제:
{task.goal}

제약:
{constraints}

후보:
---
{candidate_text}
---

JSON 객체 하나만 출력하라. Markdown code fence는 쓰지 마라.
필수 schema:
{{
  "reviewer": "{reviewer.reviewer_id}",
  "verdict": "reject | revise | pass_to_next_gate | needs_human_review",
  "defect_found": true,
  "defect_type": "결함 유형 또는 빈 문자열",
  "defect_where": "결함 위치 또는 빈 문자열",
  "reasoning": "판정 근거",
  "required_revision": "필요 수정 또는 빈 문자열",
  "confidence": 0,
  "feedback_to_thesis": "다음 생성에서 피할 규칙 또는 빈 문자열",
  "salvageable_part": "결함과 독립적으로 보존 가능한 후보의 하위 부품 또는 빈 문자열"
}}

confidence는 0~100 정수 백분율이다. 0~1 소수 척도를 쓰지 마라.
핵심 결함이면 reject, 수정 가능하면 revise, 핵심 결함을 찾지 못하면 pass_to_next_gate,
정보 부족으로 판정 자체가 불가능하면 needs_human_review로 판정하라.
reject·revise는 defect_found=true, pass_to_next_gate는 defect_found=false여야 한다.
needs_human_review는 결함을 실제 특정했으면 true, 정보 부족으로 특정하지 못했으면
false로 적어라. true이면 defect_type·defect_where를 채우고, revise이면
required_revision도 반드시 채워라.
salvageable_part는 reject·revise에서 실제로 독립 보존 가능한 부분이 있을 때만
후보 원문의 해당 내용을 자립 가능한 문장으로 적고, 없으면 빈 문자열로 두어라."""


def adversary_prompt(task: Task, reviewers: list[ReviewerSpec]) -> str:
    constraints = "\n".join(f"- {item}" for item in task.constraints) or "- 없음"
    aspects = ", ".join(reviewer.aspect for reviewer in reviewers)
    return f"""당신은 제한된 논증 결함 테스트케이스 생성기다.
목적은 심사관이 주장·논증·유추 구조 내부의 특정 오류를 정확히 탐지하는지
검증하는 것이다. 심사관을 속이거나 실제 사용자를 설득하는 것이 목적이 아니다.

원 과제:
{task.goal}

제약:
{constraints}

검사 대상 측면:
{aspects}

허용 결함 유형은 다음뿐이다:
correlation_causation, circular_reasoning, hidden_premise,
hasty_generalization, false_analogy, equivocation,
necessary_sufficient_confusion, quantifier_error

금지 범위:
- 외부 시스템 공격, 권한 우회, 도구 실행, 메모리 변조
- 사용자 조작, 보안 취약점 악용, 사회공학적 설득
- 라벨 없는 허위 주장 또는 실제 사용자 기만용 문장

candidate_text에는 테스트 대상 주장만 넣고 정답을 누설하지 마라.
hidden_oracle에는 정답표를 완전하게 기록하라.

JSON 객체 하나만 출력하라. Markdown code fence는 쓰지 마라.
{{
  "candidate_text": "심사관에게만 전달할 한국어 테스트 주장",
  "hidden_oracle": {{
    "defect_type": "허용 결함 유형 중 하나",
    "defect_where": "오류가 삽입된 정확한 위치",
    "explanation": "왜 오류인지",
    "detection_point": "심사관이 잡아야 할 핵심",
    "expected_verdict": "REJECT | REVISE"
  }}
}}"""


def boundary_translation_prompt(text: str) -> str:
    return f"""Translate the Korean source into precise English for an internal review pipeline.
Preserve every negation, quantifier, condition, exception, actor, permission,
prohibition, retention period, and rollback statement.
Do not summarize, explain, soften, strengthen, add, or remove claims.
Output only the English translation.

Korean source:
---
{text}
---"""


def post_review_audit_prompt(english_candidate: str) -> str:
    return f"""You are post_review_blindspot_auditor.
This is a non-blocking audit after the normal review gates. Find only
decision-changing omissions outside logic, scope, code, mathematics, and physics.
Relevant classes include privacy, consent, security, abuse of authority,
legal or ethical risk, and missing human recourse.

Mandatory rules:
- Cite exact candidate evidence. Never invent behavior the candidate denies.
- Do not demand optional detail.
- Do not name a jurisdiction-specific law unless the candidate supplies that jurisdiction.
- If safeguards are stated and no contrary evidence exists, pass_to_next_gate.
- If the defect belongs only to logic, scope, code, mathematics, or physics,
  pass_to_next_gate.
- reject/revise: defect_found=true; defect_type and defect_where non-empty.
- pass_to_next_gate: defect_found=false; defect_type, defect_where,
  required_revision, feedback_to_thesis, and salvageable_part are empty strings.
- revise requires non-empty required_revision.
- confidence is an integer percentage from 0 to 100, not a 0-to-1 scale.

Candidate:
---
{english_candidate}
---

Return exactly one JSON object matching the supplied schema."""


def audit_report_translation_prompt(
    *,
    korean_source: str,
    english_candidate: str,
    defect_type: str,
    defect_where: str,
    reasoning: str,
    required_revision: str,
) -> str:
    return f"""Create a concise Korean advisory report from the English audit.
This report supplements the original output and must not silently rewrite it.
Map the audit location back to the Korean source when possible.
Do not add laws, facts, or risks absent from the audit.

Korean original:
---
{korean_source}
---

English canonical text:
---
{english_candidate}
---

Audit:
- defect type: {defect_type}
- defect location: {defect_where}
- reasoning: {reasoning}
- suggested revision: {required_revision}

Output Korean only with these fields:
문제 유형:
원문 대응 위치:
판단 근거:
보강 제안:"""
