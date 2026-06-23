from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from harness.appeals import AppealService
from harness.backends import BackendError, MockBackend, OllamaBackend
from harness.casework import CaseLedger
from harness.delivery import DeliveryLedger
from harness.gates import GateLedger
from harness.gate_appeals import GateAppealCoordinator
from harness.library import LibraryLedger
from harness.model_pipeline import RoleModelPipeline
from harness.model_roster import MODEL_PROFILES
from harness.logging import EventLog
from harness.pipeline import Harness
from harness.probes import DEFAULT_PROBES
from harness.post_review_audit import PostReviewAuditService
from harness.ratchet import RatchetLedger
from harness.reviewers import DEFAULT_REVIEWERS
from harness.termination import TerminationLedger


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="analogy-harness",
        description="유추 생성·다측면 순차 심사·미끼 프로브 하네스",
    )
    parser.add_argument(
        "--log",
        default="runs/events.jsonl",
        help="JSONL 이벤트 로그 경로",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="정 생성 후 등록 심사관 순차 심사")
    _add_backend_arguments(run_parser)
    run_parser.add_argument("--task", required=True, help="과제 목표")
    run_parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="제약 조건. 여러 번 지정 가능",
    )
    run_parser.add_argument(
        "--required-aspect",
        action="append",
        default=[],
        help="반드시 관할 심사관이 있어야 하는 측면. 기본값: logic",
    )

    adversary_parser = subparsers.add_parser(
        "adversary",
        help="제한형 논증 결함 테스트케이스 생성·심사",
    )
    _add_backend_arguments(adversary_parser)
    adversary_parser.add_argument("--task", required=True, help="검증할 논증 심사 목표")
    adversary_parser.add_argument(
        "--constraint",
        action="append",
        default=[],
        help="제약 조건. 여러 번 지정 가능",
    )
    adversary_parser.add_argument(
        "--required-aspect",
        action="append",
        default=[],
        help="반드시 관할 심사관이 있어야 하는 측면. 기본값: logic",
    )

    probe_parser = subparsers.add_parser("probe", help="known-flaw 미끼 심사")
    _add_backend_arguments(probe_parser)
    probe_parser.add_argument("--probe-id", help="특정 probe만 실행")

    confirm_parser = subparsers.add_parser(
        "confirm-case",
        help="필터 통과 결함 후보를 확정 또는 기각",
    )
    confirm_parser.add_argument("--case-id", required=True)
    confirm_parser.add_argument(
        "--status",
        required=True,
        choices=["confirmed", "dismissed"],
    )
    confirm_parser.add_argument(
        "--actor-type",
        required=True,
        choices=["human", "tool"],
    )
    confirm_parser.add_argument("--actor-id", required=True)
    confirm_parser.add_argument("--evidence", required=True)
    confirm_parser.add_argument("--reason", required=True)

    show_case_parser = subparsers.add_parser(
        "show-case",
        help="사건 원장에서 케이스 현재 상태 조회",
    )
    show_case_parser.add_argument("--case-id", required=True)

    readiness_parser = subparsers.add_parser(
        "approve-feedback-readiness",
        help="부정예시 되먹임을 열 수 있는 준비 승인 사건 기록",
    )
    readiness_parser.add_argument(
        "--actor-type",
        required=True,
        choices=["human", "tool"],
    )
    readiness_parser.add_argument("--actor-id", required=True)
    readiness_parser.add_argument("--scope", required=True)
    readiness_parser.add_argument("--evidence", required=True)
    readiness_parser.add_argument("--reason", required=True)

    activation_parser = subparsers.add_parser(
        "approve-negative-example",
        help="확정 case를 생성 프롬프트 Block-rule로 명시적 활성 승인",
    )
    activation_parser.add_argument("--case-id", required=True)
    activation_parser.add_argument("--readiness-id", required=True)
    activation_parser.add_argument("--actor-id", required=True)
    activation_parser.add_argument("--reason", required=True)

    appeal_result_parser = subparsers.add_parser(
        "record-appeal-result",
        help="외부 Claude 재심 의견을 사건 원장에 재입력",
    )
    appeal_result_parser.add_argument("--appeal-id", required=True)
    appeal_result_parser.add_argument("--candidate-id", required=True)
    appeal_result_parser.add_argument(
        "--verdict",
        required=True,
        choices=["uphold", "overturn", "uncertain"],
    )
    appeal_result_parser.add_argument("--actor-id", required=True)
    appeal_result_parser.add_argument(
        "--defect",
        action="append",
        default=[],
        metavar="TYPE|WHERE|WHY",
        help="overturn 결함. 여러 번 지정 가능",
    )
    appeal_result_parser.add_argument("--salvageable-part", default="")
    appeal_result_parser.add_argument("--feedback-to-thesis", default="")

    show_gate_parser = subparsers.add_parser(
        "show-gate",
        help="Gate flow 현재 상태 조회",
    )
    show_gate_parser.add_argument("--flow-id", required=True)

    gate_decision_parser = subparsers.add_parser(
        "record-gate-decision",
        help="현재 Gate 단계의 명시적 판정 사건 기록",
    )
    gate_decision_parser.add_argument("--flow-id", required=True)
    gate_decision_parser.add_argument(
        "--decision",
        required=True,
        choices=[
            "reject",
            "revise",
            "pass_to_next_gate",
            "accepted_synthesis",
            "needs_human_review",
        ],
    )
    gate_decision_parser.add_argument(
        "--actor-type",
        required=True,
        choices=["human", "tool"],
    )
    gate_decision_parser.add_argument("--actor-id", required=True)
    gate_decision_parser.add_argument("--reason", required=True)

    gate_revision_parser = subparsers.add_parser(
        "submit-gate-revision",
        help="수정 후보를 생성·재심사한 뒤 revise 상태에 연결",
    )
    _add_backend_arguments(gate_revision_parser)
    gate_revision_parser.add_argument("--flow-id", required=True)
    gate_revision_parser.add_argument("--text", required=True)
    gate_revision_parser.add_argument(
        "--required-aspect",
        action="append",
        default=[],
        help="수정 후보를 다시 심사할 필수 측면. 기본값 logic",
    )
    gate_revision_parser.add_argument("--actor-id", required=True)
    gate_revision_parser.add_argument("--reason", required=True)

    add_part_parser = subparsers.add_parser(
        "add-library-part",
        help="재사용 부품과 필수 메타를 라이브러리에 제안 상태로 저장",
    )
    add_part_parser.add_argument("--content", required=True)
    add_part_parser.add_argument("--premise", action="append", required=True)
    add_part_parser.add_argument("--verification-context", required=True)
    add_part_parser.add_argument("--works-when", action="append", required=True)
    add_part_parser.add_argument("--fails-when", action="append", required=True)
    add_part_parser.add_argument("--purpose", required=True)
    add_part_parser.add_argument(
        "--verification-status",
        required=True,
        choices=["preserved_verified", "salvaged_unverified"],
    )
    add_part_parser.add_argument("--source-event-id", required=True)
    add_part_parser.add_argument("--source-candidate-id", required=True)
    add_part_parser.add_argument("--created-by", required=True)

    approve_purpose_parser = subparsers.add_parser(
        "approve-library-purpose",
        help="제안된 목적 주석을 별도 승인",
    )
    approve_purpose_parser.add_argument("--part-id", required=True)
    approve_purpose_parser.add_argument(
        "--actor-type",
        required=True,
        choices=["human", "tool"],
    )
    approve_purpose_parser.add_argument("--actor-id", required=True)
    approve_purpose_parser.add_argument("--reason", required=True)

    query_library_parser = subparsers.add_parser(
        "query-library",
        help="승인된 목적→조건 순서로 재사용 부품 조회",
    )
    query_library_parser.add_argument("--purpose", required=True)
    query_library_parser.add_argument("--condition", action="append", default=[])

    intake_parser = subparsers.add_parser(
        "list-library-intake",
        help="재심 등에서 들어온 메타 미완성 부품 후보 조회",
    )

    start_ratchet_parser = subparsers.add_parser(
        "start-ratchet",
        help="목적과 사용자 우선순위 줄로 래칫 세션 시작",
    )
    start_ratchet_parser.add_argument("--purpose", required=True)
    start_ratchet_parser.add_argument(
        "--priority-aspect",
        action="append",
        required=True,
    )
    start_ratchet_parser.add_argument("--actor-id", required=True)

    show_ratchet_parser = subparsers.add_parser(
        "show-ratchet",
        help="래칫 세션과 측면별 챔피언 조회",
    )
    show_ratchet_parser.add_argument("--session-id", required=True)

    admit_ratchet_parser = subparsers.add_parser(
        "admit-ratchet-candidate",
        help="Gate 3 accepted 후보를 래칫에 입장",
    )
    admit_ratchet_parser.add_argument("--session-id", required=True)
    admit_ratchet_parser.add_argument("--gate-flow-id", required=True)
    admit_ratchet_parser.add_argument("--actor-id", required=True)

    compare_ratchet_parser = subparsers.add_parser(
        "record-ratchet-comparison",
        help="현재 후보와 측면 챔피언의 상대 변화 기록",
    )
    compare_ratchet_parser.add_argument("--session-id", required=True)
    compare_ratchet_parser.add_argument("--aspect", required=True)
    compare_ratchet_parser.add_argument(
        "--result",
        required=True,
        choices=["improved", "no_meaningful_change", "regressed"],
    )
    compare_ratchet_parser.add_argument(
        "--actor-type",
        required=True,
        choices=["human", "tool"],
    )
    compare_ratchet_parser.add_argument("--actor-id", required=True)
    compare_ratchet_parser.add_argument("--reason", required=True)

    finalize_ratchet_parser = subparsers.add_parser(
        "finalize-ratchet-candidate",
        help="우선순위 줄로 전체 결과를 확정하고 챔피언 갱신",
    )
    finalize_ratchet_parser.add_argument("--session-id", required=True)
    finalize_ratchet_parser.add_argument("--actor-id", required=True)

    termination_check_parser = subparsers.add_parser(
        "check-ratchet-termination",
        help="최근 비교에서 종료 승인 가능 여부 확인",
    )
    termination_check_parser.add_argument("--session-id", required=True)

    approve_termination_parser = subparsers.add_parser(
        "approve-ratchet-termination",
        help="종료를 승인하고 잠정 챔피언 Snapshot 생성",
    )
    approve_termination_parser.add_argument("--session-id", required=True)
    approve_termination_parser.add_argument(
        "--actor-type",
        required=True,
        choices=["human", "tool"],
    )
    approve_termination_parser.add_argument("--actor-id", required=True)
    approve_termination_parser.add_argument("--reason", required=True)

    show_snapshot_parser = subparsers.add_parser(
        "show-champion-snapshot",
        help="잠정 챔피언 Snapshot 조회",
    )
    show_snapshot_parser.add_argument("--snapshot-id", required=True)

    metagame_parser = subparsers.add_parser(
        "change-metagame-status",
        help="Snapshot을 deprecated 또는 active로 전이",
    )
    metagame_parser.add_argument("--snapshot-id", required=True)
    metagame_parser.add_argument(
        "--status",
        required=True,
        choices=["active", "deprecated"],
    )
    metagame_parser.add_argument(
        "--actor-type",
        required=True,
        choices=["human", "tool"],
    )
    metagame_parser.add_argument("--actor-id", required=True)
    metagame_parser.add_argument("--reason", required=True)

    export_delivery_parser = subparsers.add_parser(
        "export-delivery",
        help="Gate 3 승인본을 최종 재감사하고 제출 묶음으로 내보내기",
    )
    _add_backend_arguments(export_delivery_parser)
    export_delivery_parser.add_argument("--flow-id", required=True)
    export_delivery_parser.add_argument(
        "--output-dir",
        default="deliveries",
        help="JSON·Markdown 제출 묶음 출력 디렉터리",
    )

    show_delivery_parser = subparsers.add_parser(
        "show-delivery",
        help="저장된 최종 제출 묶음 조회",
    )
    delivery_group = show_delivery_parser.add_mutually_exclusive_group(
        required=True
    )
    delivery_group.add_argument("--delivery-id")
    delivery_group.add_argument("--flow-id")
    return parser


def _add_backend_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--backend",
        choices=["mock", "ollama"],
        default="mock",
    )
    parser.add_argument(
        "--model-profile",
        choices=["manual", *MODEL_PROFILES],
        default="manual",
        help="검증된 역할별 모델 배치. manual이면 개별 model 인자를 사용",
    )
    parser.add_argument("--model", default="qwen3:14b")
    parser.add_argument(
        "--thesis-model",
        help="정 생성 모델. 생략 시 --model",
    )
    parser.add_argument(
        "--adversary-model",
        help="논증 결함 테스트케이스 생성 모델. 생략 시 --model",
    )
    parser.add_argument(
        "--translator-model",
        help="한국어↔영어 경계 번역 모델",
    )
    parser.add_argument(
        "--post-audit-model",
        help="비차단 영어 사후 감사 모델",
    )
    parser.add_argument(
        "--no-post-audit",
        action="store_true",
        help="프로필에 사후 감사 모델이 있어도 이번 실행에서는 생략",
    )
    parser.add_argument(
        "--reviewer-model",
        action="append",
        default=[],
        metavar="REVIEWER_ID=MODEL",
        help="심사관별 모델 지정. 여러 번 지정 가능",
    )
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--reviewer",
        action="append",
        default=[],
        help="실행할 reviewer_id. 여러 번 지정 가능. 생략 시 등록된 전원",
    )


def _make_backend(args: argparse.Namespace):
    if args.backend == "mock":
        mock = MockBackend()
        return RoleModelPipeline(
            thesis_backend=mock,
            adversary_backend=mock,
            default_reviewer_backend=mock,
        )

    def ollama(model: str) -> OllamaBackend:
        return OllamaBackend(
            model=model,
            base_url=args.ollama_url,
            timeout_seconds=args.timeout,
        )

    profile = MODEL_PROFILES.get(args.model_profile)
    reviewer_backends = (
        {
            reviewer_id: ollama(model)
            for reviewer_id, model in profile.reviewer_models.items()
        }
        if profile
        else {}
    )
    for item in args.reviewer_model:
        if "=" not in item:
            raise ValueError("--reviewer-model은 REVIEWER_ID=MODEL 형식이어야 합니다.")
        reviewer_id, model = (part.strip() for part in item.split("=", 1))
        if not reviewer_id or not model:
            raise ValueError("--reviewer-model의 reviewer ID와 model은 비어 있을 수 없습니다.")
        reviewer_backends[reviewer_id] = ollama(model)

    thesis_model = (
        args.thesis_model
        or (profile.thesis_model if profile else args.model)
    )
    adversary_model = (
        args.adversary_model
        or (profile.adversary_model if profile else args.model)
    )
    default_reviewer_model = (
        profile.default_reviewer_model if profile else args.model
    )
    translator_model = (
        args.translator_model
        or (profile.translator_model if profile else None)
    )
    post_audit_model = (
        args.post_audit_model
        or (profile.post_audit_model if profile else None)
    )
    if args.no_post_audit:
        translator_model = None
        post_audit_model = None

    return RoleModelPipeline(
        thesis_backend=ollama(thesis_model),
        adversary_backend=ollama(adversary_model),
        default_reviewer_backend=ollama(default_reviewer_model),
        reviewer_backends=reviewer_backends,
        translator_backend=ollama(translator_model) if translator_model else None,
        post_audit_backend=ollama(post_audit_model) if post_audit_model else None,
    )


def main(argv: list[str] | None = None) -> int:
    _configure_utf8_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "show-delivery":
            packet = DeliveryLedger(Path(args.log)).get(
                delivery_id=args.delivery_id or "",
                flow_id=args.flow_id or "",
            )
            print(json.dumps(packet.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "export-delivery":
            backend = _make_backend(args)
            if (
                not isinstance(backend, RoleModelPipeline)
                or not backend.post_audit_enabled
            ):
                raise ValueError(
                    "최종 제출에는 translator와 post-audit 모델이 필요합니다. "
                    "confirmed-local 프로필 또는 두 모델 인자를 지정하세요."
                )
            assert backend.translator_backend is not None
            assert backend.post_audit_backend is not None
            packet = DeliveryLedger(Path(args.log)).create(
                flow_id=args.flow_id,
                auditor=PostReviewAuditService(
                    translator=backend.translator_backend,  # type: ignore[arg-type]
                    auditor=backend.post_audit_backend,  # type: ignore[arg-type]
                    events=EventLog(Path(args.log)),
                ),
                output_dir=Path(args.output_dir),
            )
            print(json.dumps(packet.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "show-case":
            state = CaseLedger(Path(args.log)).get(args.case_id)
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "confirm-case":
            state = CaseLedger(Path(args.log)).confirm(
                case_id=args.case_id,
                new_status=args.status,
                actor_type=args.actor_type,
                actor_id=args.actor_id,
                evidence=args.evidence,
                reason=args.reason,
            )
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "approve-feedback-readiness":
            event = CaseLedger(Path(args.log)).record_feedback_readiness(
                actor_type=args.actor_type,
                actor_id=args.actor_id,
                scope=args.scope,
                evidence=args.evidence,
                reason=args.reason,
            )
            print(json.dumps(event, ensure_ascii=False, indent=2))
            return 0

        if args.command == "approve-negative-example":
            state = CaseLedger(Path(args.log)).approve_negative_example(
                case_id=args.case_id,
                readiness_id=args.readiness_id,
                actor_id=args.actor_id,
                reason=args.reason,
            )
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "record-appeal-result":
            defects = []
            for raw in args.defect:
                parts = [part.strip() for part in raw.split("|", 2)]
                if len(parts) != 3:
                    raise ValueError("--defect는 TYPE|WHERE|WHY 형식이어야 합니다.")
                defects.append(
                    {"type": parts[0], "where": parts[1], "why": parts[2]}
                )
            event = AppealService(Path(args.log)).import_result(
                appeal_id=args.appeal_id,
                candidate_id=args.candidate_id,
                verdict=args.verdict,
                actor_id=args.actor_id,
                defects=defects,
                salvageable_part=args.salvageable_part,
                feedback_to_thesis=args.feedback_to_thesis,
            )
            print(json.dumps(event, ensure_ascii=False, indent=2))
            return 0

        if args.command == "show-gate":
            state = GateLedger(Path(args.log)).get(args.flow_id)
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "record-gate-decision":
            state, appeal_packet = GateAppealCoordinator(
                Path(args.log)
            ).record_decision(
                flow_id=args.flow_id,
                decision=args.decision,
                actor_type=args.actor_type,
                actor_id=args.actor_id,
                reason=args.reason,
            )
            print(
                json.dumps(
                    {
                        **state.to_dict(),
                        "appeal_packet": (
                            appeal_packet.to_dict()
                            if appeal_packet is not None
                            else None
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "add-library-part":
            part = LibraryLedger(Path(args.log)).add_part(
                content=args.content,
                premises=args.premise,
                verification_context=args.verification_context,
                works_when=args.works_when,
                fails_when=args.fails_when,
                purpose=args.purpose,
                verification_status=args.verification_status,
                source_event_id=args.source_event_id,
                source_candidate_id=args.source_candidate_id,
                created_by=args.created_by,
            )
            print(json.dumps(part.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "approve-library-purpose":
            part = LibraryLedger(Path(args.log)).approve_purpose(
                part_id=args.part_id,
                actor_type=args.actor_type,
                actor_id=args.actor_id,
                reason=args.reason,
            )
            print(json.dumps(part.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "query-library":
            matches = LibraryLedger(Path(args.log)).query(
                purpose=args.purpose,
                conditions=args.condition,
            )
            print(
                json.dumps(
                    {
                        "purpose": args.purpose,
                        "conditions": args.condition,
                        "matches": [item.to_dict() for item in matches],
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "list-library-intake":
            candidates = LibraryLedger(Path(args.log)).intake_candidates()
            print(json.dumps({"candidates": candidates}, ensure_ascii=False, indent=2))
            return 0

        if args.command == "start-ratchet":
            state = RatchetLedger(Path(args.log)).start(
                purpose=args.purpose,
                priority_line=args.priority_aspect,
                actor_id=args.actor_id,
            )
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "show-ratchet":
            state = RatchetLedger(Path(args.log)).get(args.session_id)
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "admit-ratchet-candidate":
            state = RatchetLedger(Path(args.log)).admit_candidate(
                session_id=args.session_id,
                gate_flow_id=args.gate_flow_id,
                actor_id=args.actor_id,
            )
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "record-ratchet-comparison":
            state = RatchetLedger(Path(args.log)).record_comparison(
                session_id=args.session_id,
                aspect=args.aspect,
                result=args.result,
                actor_type=args.actor_type,
                actor_id=args.actor_id,
                reason=args.reason,
            )
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "finalize-ratchet-candidate":
            state = RatchetLedger(Path(args.log)).finalize_candidate(
                session_id=args.session_id,
                actor_id=args.actor_id,
            )
            print(json.dumps(state.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "check-ratchet-termination":
            result = TerminationLedger(Path(args.log)).eligibility(args.session_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0

        if args.command == "approve-ratchet-termination":
            snapshot = TerminationLedger(Path(args.log)).approve(
                session_id=args.session_id,
                actor_type=args.actor_type,
                actor_id=args.actor_id,
                reason=args.reason,
            )
            print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "show-champion-snapshot":
            snapshot = TerminationLedger(Path(args.log)).get(args.snapshot_id)
            print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))
            return 0

        if args.command == "change-metagame-status":
            snapshot = TerminationLedger(Path(args.log)).change_status(
                snapshot_id=args.snapshot_id,
                new_status=args.status,
                actor_type=args.actor_type,
                actor_id=args.actor_id,
                reason=args.reason,
            )
            print(json.dumps(snapshot.to_dict(), ensure_ascii=False, indent=2))
            return 0

        reviewer_ids = args.reviewer or None
        if args.command == "probe" and not args.reviewer:
            reviewer_ids = [reviewer.reviewer_id for reviewer in DEFAULT_REVIEWERS]

        harness = Harness(
            _make_backend(args),
            Path(args.log),
            reviewer_ids=reviewer_ids,
        )
        if args.command == "run":
            candidate, review_batch = harness.run(
                args.task,
                args.constraint,
                args.required_aspect or ["logic"],
            )
            print(
                json.dumps(
                    {
                        "candidate": {
                            "candidate_id": candidate.candidate_id,
                            "text": candidate.text,
                        },
                        "review_batch": review_batch.to_dict(),
                        "gate_flow": (
                            harness.last_gate_flow.to_dict()
                            if harness.last_gate_flow
                            else None
                        ),
                        "appeal_packet": (
                            harness.last_appeal_packet.to_dict()
                            if harness.last_appeal_packet
                            else None
                        ),
                        "post_review_audit": (
                            harness.last_post_review_audit.to_dict()
                            if harness.last_post_review_audit
                            else None
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "adversary":
            report = harness.run_adversary(
                args.task,
                args.constraint,
                args.required_aspect or ["logic"],
            )
            print(
                json.dumps(
                    {
                        "case_report": report.to_dict(),
                        "appeal_packet": (
                            harness.last_appeal_packet.to_dict()
                            if harness.last_appeal_packet
                            else None
                        ),
                        "post_review_audit": (
                            harness.last_post_review_audit.to_dict()
                            if harness.last_post_review_audit
                            else None
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        if args.command == "submit-gate-revision":
            candidate, review_batch = harness.submit_gate_revision(
                flow_id=args.flow_id,
                revised_text=args.text,
                actor_id=args.actor_id,
                reason=args.reason,
                required_aspects=args.required_aspect or ["logic"],
            )
            print(
                json.dumps(
                    {
                        "candidate": {
                            "candidate_id": candidate.candidate_id,
                            "text": candidate.text,
                        },
                        "review_batch": review_batch.to_dict(),
                        "gate_flow": (
                            harness.last_gate_flow.to_dict()
                            if harness.last_gate_flow
                            else None
                        ),
                        "appeal_packet": (
                            harness.last_appeal_packet.to_dict()
                            if harness.last_appeal_packet
                            else None
                        ),
                        "post_review_audit": (
                            harness.last_post_review_audit.to_dict()
                            if harness.last_post_review_audit
                            else None
                        ),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return 0

        probes = DEFAULT_PROBES
        if args.probe_id:
            probes = [probe for probe in probes if probe.probe_id == args.probe_id]
            if not probes:
                parser.error(f"알 수 없는 probe-id: {args.probe_id}")

        results = [harness.run_probe(probe) for probe in probes]
        detected = sum(result.detected for result in results)
        correct = sum(result.correct for result in results)
        print(
            json.dumps(
                {
                    "backend": args.backend,
                    "model_profile": (
                        args.model_profile if args.backend == "ollama" else None
                    ),
                    "reviewer_models": (
                        {
                            reviewer.reviewer_id: getattr(
                                (
                                    harness.backend.reviewer_backend(
                                        reviewer.reviewer_id
                                    )
                                    if isinstance(
                                        harness.backend,
                                        RoleModelPipeline,
                                    )
                                    else harness.backend
                                ),
                                "model",
                                None,
                            )
                            for reviewer in harness.reviewers
                        }
                        if args.backend == "ollama"
                        else {}
                    ),
                    "summary": {
                        "total": len(results),
                        "detected": detected,
                        "all_detected": detected == len(results),
                        "correct": correct,
                        "all_correct": correct == len(results),
                    },
                    "results": [result.to_dict() for result in results],
                },
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0 if correct == len(results) else 2
    except (BackendError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1


def _configure_utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
