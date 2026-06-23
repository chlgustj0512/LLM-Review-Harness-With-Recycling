from __future__ import annotations

from typing import Any


def review_batch_payload(
    candidate_id: str,
    status: str = "clear",
) -> dict[str, Any]:
    jurisdiction = {
        "reviewer": "logic_reviewer",
        "aspect": "logic",
        "applicable": status != "empty_aspect",
        "reasoning": "테스트 관할 판정",
        "confidence": 95,
    }
    reviews: list[dict[str, Any]] = []
    if status == "clear":
        reviews = [_review(candidate_id, "logic_reviewer", "pass_to_next_gate")]
    elif status == "objections":
        reviews = [
            _review(
                candidate_id,
                "logic_reviewer",
                "reject",
                dependency="independent",
            )
        ]
    elif status == "dependent_core_blocked":
        reviews = [_review(candidate_id, "logic_reviewer", "reject")]
    elif status == "conflict":
        reviews = [
            _review(candidate_id, "logic_reviewer", "pass_to_next_gate"),
            _review(
                candidate_id,
                "logic_reviewer_2",
                "reject",
                dependency="independent",
            ),
        ]
    elif status == "human_review":
        reviews = [_review(candidate_id, "logic_reviewer", "needs_human_review")]
    elif status != "empty_aspect":
        raise ValueError(f"지원하지 않는 테스트 ReviewBatch status: {status}")

    jurisdictions = [jurisdiction]
    if status == "conflict":
        jurisdictions.append(
            {
                **jurisdiction,
                "reviewer": "logic_reviewer_2",
            }
        )
    return {
        "candidate_id": candidate_id,
        "required_aspects": ["logic"],
        "jurisdictions": jurisdictions,
        "reviews": reviews,
        "empty_aspects": ["logic"] if status == "empty_aspect" else [],
        "conflicting_aspects": ["logic"] if status == "conflict" else [],
        "dependent_core_blocked": (
            ["logic"] if status == "dependent_core_blocked" else []
        ),
        "status": status,
        "gate_decision": None,
    }


def _review(
    candidate_id: str,
    reviewer: str,
    verdict: str,
    *,
    dependency: str = "dependent_core",
) -> dict[str, Any]:
    defect_found = verdict in {"reject", "revise"}
    return {
        "candidate_id": candidate_id,
        "reviewer": reviewer,
        "aspect": "logic",
        "dependency": dependency,
        "verdict": verdict,
        "defect_found": defect_found,
        "defect_type": "테스트 결함" if defect_found else "",
        "defect_where": "후보 본문" if defect_found else "",
        "reasoning": "테스트 심사 근거",
        "required_revision": "수정 필요" if verdict == "revise" else "",
        "confidence": 90,
        "feedback_to_thesis": "",
        "salvageable_part": "",
    }
