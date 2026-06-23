from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from abc import ABC, abstractmethod
from typing import Any

from harness.models import (
    ArgumentDefectOracle,
    ArgumentDefectTestCase,
    NegativeExampleRule,
    ReviewerSpec,
    Task,
)
from harness.prompts import (
    adversary_prompt,
    jurisdiction_prompt,
    review_prompt,
    thesis_prompt,
)

JURISDICTION_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "applicable": {"type": "boolean"},
        "reasoning": {"type": "string"},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
    },
    "required": ["applicable", "reasoning", "confidence"],
    "additionalProperties": False,
}

REVIEW_JSON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reviewer": {"type": "string"},
        "verdict": {
            "type": "string",
            "enum": [
                "reject",
                "revise",
                "pass_to_next_gate",
                "needs_human_review",
            ],
        },
        "defect_found": {"type": "boolean"},
        "defect_type": {"type": "string"},
        "defect_where": {"type": "string"},
        "reasoning": {"type": "string"},
        "required_revision": {"type": "string"},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "feedback_to_thesis": {"type": "string"},
        "salvageable_part": {"type": "string"},
    },
    "required": [
        "reviewer",
        "verdict",
        "defect_found",
        "defect_type",
        "defect_where",
        "reasoning",
        "required_revision",
        "confidence",
        "feedback_to_thesis",
        "salvageable_part",
    ],
    "additionalProperties": False,
}

ARGUMENT_DEFECT_TEST_CASE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "candidate_text": {"type": "string"},
        "hidden_oracle": {
            "type": "object",
            "properties": {
                "defect_type": {
                    "type": "string",
                    "enum": [
                        "correlation_causation",
                        "circular_reasoning",
                        "hidden_premise",
                        "hasty_generalization",
                        "false_analogy",
                        "equivocation",
                        "necessary_sufficient_confusion",
                        "quantifier_error",
                    ],
                },
                "defect_where": {"type": "string"},
                "explanation": {"type": "string"},
                "detection_point": {"type": "string"},
                "expected_verdict": {
                    "type": "string",
                    "enum": ["REJECT", "REVISE"],
                },
            },
            "required": [
                "defect_type",
                "defect_where",
                "explanation",
                "detection_point",
                "expected_verdict",
            ],
            "additionalProperties": False,
        },
    },
    "required": ["candidate_text", "hidden_oracle"],
    "additionalProperties": False,
}


class BackendError(RuntimeError):
    pass


class Backend(ABC):
    name: str

    @abstractmethod
    def generate_candidate(
        self,
        task: Task,
        negative_examples: list[NegativeExampleRule] | None = None,
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def generate_adversarial_candidate(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> str:
        raise NotImplementedError

    def generate_argument_defect_test_case(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> ArgumentDefectTestCase:
        test_case = ArgumentDefectTestCase(
            candidate_text=self.generate_adversarial_candidate(task, reviewers),
            hidden_oracle=ArgumentDefectOracle(
                defect_type="hidden_premise",
                defect_where="핵심 결론을 지지하는 전제",
                explanation="결론에 필요한 전제가 후보에 명시되거나 검증되지 않았다.",
                detection_point="결론이 성립하려면 추가 전제가 필요한지 확인한다.",
                expected_verdict="REVISE",
            ),
        )
        test_case.validate()
        return test_case

    @abstractmethod
    def assess_jurisdiction(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        raise NotImplementedError

    @abstractmethod
    def review_candidate(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        raise NotImplementedError


class MockBackend(Backend):
    name = "mock"

    def generate_candidate(
        self,
        task: Task,
        negative_examples: list[NegativeExampleRule] | None = None,
    ) -> str:
        rules = negative_examples or []
        rule_note = (
            f"\n활성 Block-rule {len(rules)}개를 회피한다."
            if rules
            else ""
        )
        return (
            f"핵심 제안: {task.goal}을 작은 실험으로 검증한다.\n"
            "작동 원리: 한 번에 한 변수만 바꾸고 이전 결과와 비교한다.\n"
            "적용 조건: 결과를 관찰할 수 있고 변경을 되돌릴 수 있어야 한다.\n"
            "실패 조건: 외부 변수가 통제되지 않으면 인과 해석을 중단한다.\n"
            f"검증 방법: 변경 전후를 같은 조건에서 반복 비교한다.{rule_note}"
        )

    def generate_adversarial_candidate(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> str:
        return (
            "핵심 제안: 검증된 성공 사례 하나를 전 조직의 표준으로 즉시 채택한다.\n"
            "작동 원리: 성공한 방식이므로 같은 결과를 반복해서 만든다.\n"
            "적용 조건: 모든 구성원이 지침을 그대로 따른다.\n"
            "실패 조건: 지침을 따르지 않을 때만 실패한다.\n"
            "검증 방법: 도입 후 성공 사례가 다시 나타나는지 확인한다."
        )

    def generate_argument_defect_test_case(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> ArgumentDefectTestCase:
        test_case = ArgumentDefectTestCase(
            candidate_text=self.generate_adversarial_candidate(task, reviewers),
            hidden_oracle=ArgumentDefectOracle(
                defect_type="hasty_generalization",
                defect_where="성공 사례 하나를 전 조직의 표준으로 즉시 채택하는 결론",
                explanation="단일 성공 사례만으로 모든 조직에서 같은 결과가 난다고 일반화했다.",
                detection_point="표본 하나에서 보편적 결론으로 확장한 부분을 탐지한다.",
                expected_verdict="REJECT",
            ),
        )
        test_case.validate()
        return test_case

    def assess_jurisdiction(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        if reviewer.aspect == "logic":
            applicable = bool(candidate_text.strip())
            reason = "후보가 결론과 근거를 포함하므로 논리 측면의 관할이다."
        elif reviewer.aspect == "scope":
            markers = (
                "모든",
                "반드시",
                "항상",
                "적용 조건",
                "실패 조건",
                "범위",
                "일반화",
            )
            applicable = any(marker in candidate_text for marker in markers)
            reason = (
                "범위 표현이나 적용·실패 조건이 있어 scope 측면의 관할이다."
                if applicable
                else "범위를 판단할 명시적 주장이나 조건이 없다."
            )
        elif reviewer.aspect == "blindspot":
            applicable = True
            reason = "빈 측면 탐색은 후보 내용과 무관하게 항상 관할이다."
        elif reviewer.aspect == "code":
            markers = ("```", "def ", "class ", "assert ", "python", "코드", "함수")
            applicable = any(marker in candidate_text.lower() for marker in markers)
            reason = (
                "실행 코드나 테스트 단서가 있어 code 측면의 관할이다."
                if applicable
                else "후보에서 실행 코드나 테스트 단서를 찾지 못했다."
            )
        elif reviewer.aspect == "math":
            markers = ("sqrt", "방정식", "부등식", "수열", "합", "증명", "=", "∑")
            applicable = any(marker in candidate_text.lower() for marker in markers)
            reason = (
                "수식·계산·증명 단서가 있어 math 측면의 관할이다."
                if applicable
                else "후보에서 수식·계산·증명 단서를 찾지 못했다."
            )
        elif reviewer.aspect == "physics":
            markers = ("힘", "질량", "속력", "가속도", "에너지", "차원", "kg", " m/s")
            applicable = any(marker in candidate_text.lower() for marker in markers)
            reason = (
                "물리량·법칙·단위 단서가 있어 physics 측면의 관할이다."
                if applicable
                else "후보에서 물리량·법칙·단위 단서를 찾지 못했다."
            )
        else:
            applicable = reviewer.aspect.lower() in candidate_text.lower()
            reason = (
                f"후보에 {reviewer.aspect} 측면의 명시적 단서가 있다."
                if applicable
                else f"후보에서 {reviewer.aspect} 측면의 단서를 찾지 못했다."
            )
        return {
            "applicable": applicable,
            "reasoning": reason,
            "confidence": 95,
        }

    def review_candidate(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        if reviewer.aspect == "scope":
            return self._review_scope(candidate_text, reviewer)
        if reviewer.aspect == "logic":
            return self._review_logic(candidate_text, reviewer)
        if reviewer.aspect == "code":
            return self._review_code(candidate_text, reviewer)
        if reviewer.aspect == "math":
            return self._review_math(candidate_text, reviewer)
        if reviewer.aspect == "physics":
            return self._review_physics(candidate_text, reviewer)
        if reviewer.aspect == "blindspot":
            return self._review_blindspot(candidate_text, reviewer)
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": "pass_to_next_gate",
            "defect_found": False,
            "defect_type": "",
            "defect_where": "",
            "reasoning": f"mock backend에서 {reviewer.aspect} 측면의 결함을 발견하지 못했다.",
            "required_revision": "",
            "confidence": 70,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }

    def _review_blindspot(
        self,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        invasive_collection = (
            (
                "키 입력" in candidate_text
                or "키스트로크" in candidate_text
                or "개인 메시지" in candidate_text
                or "정확한 위치" in candidate_text
            )
            and ("동의 없이" in candidate_text or "고지 없이" in candidate_text)
        )
        unrestricted_retention = (
            "영구 보관" in candidate_text
            or "삭제하지 않" in candidate_text
            or "접근 제한 없이" in candidate_text
        )
        if invasive_collection or unrestricted_retention:
            return {
                "reviewer": reviewer.reviewer_id,
                "verdict": "reject",
                "defect_found": True,
                "defect_type": "개인정보·동의·접근통제 누락",
                "defect_where": "직원 감시 데이터를 무고지 수집·무기한 보관·공개하는 부분",
                "reasoning": (
                    "업무 목적을 넘어선 민감 데이터를 당사자 동의와 접근 제한 없이 "
                    "수집·보관하므로 개인정보와 권한 남용 위험이 결론을 무너뜨린다."
                ),
                "required_revision": (
                    "수집 범위를 업무상 필요한 최소 데이터로 줄이고 명시적 고지·동의, "
                    "보관 기한, 역할 기반 접근통제, 삭제·이의제기 절차를 둬야 한다."
                ),
                "confidence": 99,
                "feedback_to_thesis": (
                    "사람을 관찰하는 제안은 데이터 최소화·동의·접근통제·삭제 경로를 "
                    "명시한다."
                ),
                "salvageable_part": "",
            }
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": "pass_to_next_gate",
            "defect_found": False,
            "defect_type": "",
            "defect_where": "",
            "reasoning": "다른 심사 측면 밖에서 결정을 바꾸는 구체적 누락을 발견하지 못했다.",
            "required_revision": "",
            "confidence": 80,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }

    def _review_physics(
        self,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        bad_kinetic_dimension = (
            "K = (1/2)mv" in candidate_text
            and "K = (1/2)mv^2" not in candidate_text
            and "kg·m/s" in candidate_text
            and "줄(J)" in candidate_text
        )
        if bad_kinetic_dimension:
            return {
                "reviewer": reviewer.reviewer_id,
                "verdict": "revise",
                "defect_found": True,
                "defect_type": "차원 불일치",
                "defect_where": "운동에너지 식에서 v²를 누락한 부분",
                "reasoning": "kg·m/s는 운동량 차원이며 에너지 J=kg·m²/s²와 다르다.",
                "required_revision": "운동에너지를 K=(1/2)mv²로 고치고 단위를 다시 검산한다.",
                "confidence": 99,
                "feedback_to_thesis": "물리식은 기본 차원으로 환원해 양변 단위를 검산한다.",
                "salvageable_part": "",
            }
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": "pass_to_next_gate",
            "defect_found": False,
            "defect_type": "",
            "defect_where": "",
            "reasoning": "지정된 물리 법칙·차원·가정 결함을 발견하지 못했다.",
            "required_revision": "",
            "confidence": 80,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }

    def _review_math(
        self,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        extraneous_root = (
            "sqrt(x + 1)" in candidate_text
            and "x = 0" in candidate_text
            and "x = 3" in candidate_text
        )
        if extraneous_root:
            return {
                "reviewer": reviewer.reviewer_id,
                "verdict": "revise",
                "defect_found": True,
                "defect_type": "가짜해",
                "defect_where": "제곱 뒤 x=0을 원래 방정식에 대입하지 않은 부분",
                "reasoning": "x=0은 원래 식의 우변이 음수이며 방정식을 만족하지 않는다.",
                "required_revision": "제곱으로 얻은 근을 원래 방정식에 대입해 x=3만 남긴다.",
                "confidence": 99,
                "feedback_to_thesis": "비동치 변형 뒤에는 후보해를 원래 식으로 검산한다.",
                "salvageable_part": "",
            }
        missing_domain = (
            "(x-2)/(x-2)" in candidate_text
            and "모든 실수" in candidate_text
        )
        if missing_domain:
            return {
                "reviewer": reviewer.reviewer_id,
                "verdict": "revise",
                "defect_found": True,
                "defect_type": "정의역 누락",
                "defect_where": "x=2에서 분모가 0이 되는 경우를 포함한 결론",
                "reasoning": "x=2에서는 식이 정의되지 않으므로 해가 모든 실수일 수 없다.",
                "required_revision": "정의역에서 x=2를 제외하고 해를 다시 적는다.",
                "confidence": 99,
                "feedback_to_thesis": "약분 전 원래 식의 정의역 제한을 보존한다.",
                "salvageable_part": "",
            }
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": "pass_to_next_gate",
            "defect_found": False,
            "defect_type": "",
            "defect_where": "",
            "reasoning": "지정된 수학 계산·정의역·가짜해 결함을 발견하지 못했다.",
            "required_revision": "",
            "confidence": 80,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }

    def _review_code(
        self,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        empty_average_failure = (
            "sum(values) / len(values)" in candidate_text
            and ("average([])" in candidate_text or "빈 목록" in candidate_text)
            and "if not values" not in candidate_text
        )
        if empty_average_failure:
            return {
                "reviewer": reviewer.reviewer_id,
                "verdict": "revise",
                "defect_found": True,
                "defect_type": "ZeroDivisionError",
                "defect_where": "빈 목록에서 len(values)가 0이 되는 평균 계산",
                "reasoning": "빈 목록은 0으로 나누게 되어 실행 중 예외가 발생한다.",
                "required_revision": "빈 목록을 먼저 처리한 뒤 평균을 계산해야 한다.",
                "confidence": 99,
                "feedback_to_thesis": "분모가 입력 길이인 코드는 빈 입력을 별도로 처리한다.",
                "salvageable_part": "",
            }
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": "pass_to_next_gate",
            "defect_found": False,
            "defect_type": "",
            "defect_where": "",
            "reasoning": "지정된 코드 실행·경계값 결함을 발견하지 못했다.",
            "required_revision": "",
            "confidence": 80,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }

    def _review_logic(
        self,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        lowered = candidate_text.lower()
        patterns = [
            (
                ("아침형" in candidate_text and "성공" in candidate_text),
                "상관관계의 인과 오인",
                "아침형 생활과 성공의 관계를 직접 인과로 단정한 부분",
            ),
            (
                ("모든" in candidate_text and ("한 사례" in candidate_text or "사례 하나" in candidate_text)),
                "성급한 일반화",
                "단일 사례에서 모든 대상으로 일반화한 부분",
            ),
            (
                ("옳기 때문에 옳" in candidate_text or "참이므로 참" in candidate_text),
                "순환논증",
                "결론을 전제로 다시 사용한 부분",
            ),
            (
                ("therefore" in lowered and "because it is true" in lowered),
                "순환논증",
                "결론을 근거로 재사용한 부분",
            ),
            (
                ("민수는 매일 운동" in candidate_text and "민수는 건강" in candidate_text),
                "정당화되지 않은 숨은 전제",
                "운동한다는 사실만으로 건강하다고 결론낸 부분",
            ),
            (
                ("깃털 100만" in candidate_text and "무게가 거의 없" in candidate_text),
                "애매어",
                "'가볍다'의 상대적 의미를 무게가 없다는 뜻으로 바꾼 부분",
            ),
            (
                ("어떤 학생" in candidate_text and "모든 학생" in candidate_text),
                "양화사 오류",
                "존재 명제를 보편 명제로 확장한 부분",
            ),
            (
                ("회사는 가족" in candidate_text and "절대 해고" in candidate_text),
                "거짓 유추",
                "가족과 회사의 차이를 무시하고 결론을 옮긴 부분",
            ),
            (
                ("합격하려면" in candidate_text and "시험을 봤다" in candidate_text),
                "필요조건과 충분조건 혼동",
                "시험 응시라는 필요조건만으로 합격을 확정한 부분",
            ),
        ]
        for matched, defect_type, where in patterns:
            if matched:
                return {
                    "reviewer": reviewer.reviewer_id,
                    "verdict": "reject",
                    "defect_found": True,
                    "defect_type": defect_type,
                    "defect_where": where,
                    "reasoning": f"{defect_type} 결함으로 결론이 전제에서 따라오지 않는다.",
                    "required_revision": "독립 근거와 반례 검사를 추가하고 결론 범위를 줄여야 한다.",
                    "confidence": 98,
                    "feedback_to_thesis": f"{defect_type} 결함을 피하고 독립 근거를 요구한다.",
                    "salvageable_part": "",
                }
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": "pass_to_next_gate",
            "defect_found": False,
            "defect_type": "",
            "defect_where": "",
            "reasoning": "지정된 논리 결함을 발견하지 못했고 적용·실패·검증 조건이 제시되었다.",
            "required_revision": "",
            "confidence": 80,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }

    def _review_scope(
        self,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        explicit_no_safeguards = (
            "예외는 없" in candidate_text
            or "예외가 없" in candidate_text
            or "실패 조건도 존재하지 않" in candidate_text
            or "실패 조건이 없" in candidate_text
        )
        empirical_scope_claim = any(
            marker in candidate_text
            for marker in ("조직", "산업", "국가", "도입", "생산성", "사무실")
        )
        overgeneralized = (
            empirical_scope_claim
            and
            ("모든" in candidate_text or "반드시" in candidate_text)
            and (
                explicit_no_safeguards
                or (
                    "적용 조건" not in candidate_text
                    and "예외" not in candidate_text
                )
            )
        )
        if overgeneralized:
            return {
                "reviewer": reviewer.reviewer_id,
                "verdict": "revise",
                "defect_found": True,
                "defect_type": "적용 범위 과잉",
                "defect_where": "모든 대상 또는 필연적 성공으로 확장한 부분",
                "reasoning": "일부 근거에서 보편적 결론으로 확장했지만 적용 조건과 예외가 없다.",
                "required_revision": "적용 대상을 한정하고 예외와 실패 조건을 명시해야 한다.",
                "confidence": 96,
                "feedback_to_thesis": "보편 표현에는 적용 조건과 예외를 함께 제시한다.",
                "salvageable_part": "",
            }
        return {
            "reviewer": reviewer.reviewer_id,
            "verdict": "pass_to_next_gate",
            "defect_found": False,
            "defect_type": "",
            "defect_where": "",
            "reasoning": "담당 범위에서 적용 조건과 실패 조건이 제시되었거나 과잉 확장이 없다.",
            "required_revision": "",
            "confidence": 82,
            "feedback_to_thesis": "",
            "salvageable_part": "",
        }


class OllamaBackend(Backend):
    name = "ollama"

    def __init__(
        self,
        model: str,
        base_url: str = "http://127.0.0.1:11434",
        timeout_seconds: int = 300,
    ) -> None:
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def _generate(
        self,
        prompt: str,
        *,
        output_format: str | dict[str, Any] | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "think": False,
            "options": {"temperature": 0},
        }
        if output_format is not None:
            payload["format"] = output_format

        raw = self._request(payload)
        text = str(raw.get("response", "")).strip()

        # gpt-oss Harmony renderer는 JSON Schema format과 함께 호출하면 토큰을
        # 생성하고도 response를 비우는 경우가 있다. 프롬프트 자체에도 동일한
        # JSON 계약이 있으므로, 이 경우에만 schema 강제를 제거해 한 번 재시도한다.
        if not text and isinstance(output_format, dict):
            fallback_payload = dict(payload)
            fallback_payload.pop("format", None)
            raw = self._request(fallback_payload)
            text = str(raw.get("response", "")).strip()
        if not text:
            raise BackendError("Ollama가 빈 응답을 반환했습니다.")
        return text

    def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        request = urllib.request.Request(
            f"{self.base_url}/api/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise BackendError(f"Ollama 호출 실패: {exc}") from exc

    def generate_candidate(
        self,
        task: Task,
        negative_examples: list[NegativeExampleRule] | None = None,
    ) -> str:
        return _strip_thinking(
            self._generate(thesis_prompt(task, negative_examples))
        )

    def generate_adversarial_candidate(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> str:
        return _strip_thinking(self._generate(adversary_prompt(task, reviewers)))

    def generate_argument_defect_test_case(
        self,
        task: Task,
        reviewers: list[ReviewerSpec],
    ) -> ArgumentDefectTestCase:
        raw = _extract_json_object(
            _strip_thinking(
                self._generate(
                    adversary_prompt(task, reviewers),
                    output_format=ARGUMENT_DEFECT_TEST_CASE_SCHEMA,
                )
            )
        )
        oracle_raw = raw.get("hidden_oracle")
        if not isinstance(oracle_raw, dict):
            raise BackendError("논증 결함 테스트의 hidden_oracle이 없습니다.")
        test_case = ArgumentDefectTestCase(
            candidate_text=str(raw.get("candidate_text", "")).strip(),
            hidden_oracle=ArgumentDefectOracle(
                defect_type=str(oracle_raw.get("defect_type", "")).strip(),
                defect_where=str(oracle_raw.get("defect_where", "")).strip(),
                explanation=str(oracle_raw.get("explanation", "")).strip(),
                detection_point=str(oracle_raw.get("detection_point", "")).strip(),
                expected_verdict=str(
                    oracle_raw.get("expected_verdict", "")
                ).strip(),
            ),
        )
        test_case.validate()
        return test_case

    def complete(
        self,
        prompt: str,
        *,
        output_format: str | dict[str, Any] | None = None,
    ) -> str:
        return _strip_thinking(
            self._generate(prompt, output_format=output_format)
        )

    def assess_jurisdiction(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        text = _strip_thinking(
            self._generate(
                jurisdiction_prompt(task, candidate_text, reviewer),
                output_format=JURISDICTION_JSON_SCHEMA,
            )
        )
        return _extract_json_object(text)

    def review_candidate(
        self,
        task: Task,
        candidate_text: str,
        reviewer: ReviewerSpec,
    ) -> dict[str, Any]:
        text = _strip_thinking(
            self._generate(
                review_prompt(task, candidate_text, reviewer),
                output_format=REVIEW_JSON_SCHEMA,
            )
        )
        return _extract_json_object(text)


def _strip_thinking(text: str) -> str:
    return re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE).strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise BackendError("심사 응답에서 JSON 객체를 찾지 못했습니다.")
        try:
            value = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise BackendError(f"심사 JSON 해석 실패: {exc}") from exc

    if not isinstance(value, dict):
        raise BackendError("심사 응답은 JSON 객체여야 합니다.")
    return value
