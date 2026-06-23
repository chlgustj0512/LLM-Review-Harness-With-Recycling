from __future__ import annotations

from collections.abc import Iterable

from harness.models import ReviewerSpec


DEFAULT_REVIEWERS = [
    ReviewerSpec(
        reviewer_id="logic_reviewer",
        aspect="logic",
        description="전제–결론 연결과 추론 건전성을 검사한다.",
        instructions=(
            "상관관계의 인과 오인, 순환논증, 숨은 전제, 성급한 일반화, "
            "반례에 취약한 추론을 검사하라."
        ),
        dependency="dependent_core",
    ),
    ReviewerSpec(
        reviewer_id="scope_reviewer",
        aspect="scope",
        description="주장의 적용 범위와 실패 조건을 검사한다.",
        instructions=(
            "결론이 전제보다 넓어지는지, 모든·반드시 같은 양화사가 정당한지, "
            "적용 조건·예외·실패 조건이 빠졌는지 검사하라. 범주형 경계와 "
            "사람 처리·되돌림 경로가 충분하면 임의의 수치 기준, 절대 임계값, "
            "과도한 세부 정의를 추가로 요구하지 마라. 모든·반드시·항상 같은 "
            "보편 양화사, 예외 없음, 실패 조건 없음은 명백한 scope 관할이다. "
            "일반화 오류와 겹치더라도 logic 측면으로 떠넘기지 마라."
        ),
        dependency="independent",
    ),
    ReviewerSpec(
        reviewer_id="code_reviewer",
        aspect="code",
        description="코드의 실행 가능성·테스트·회귀·보안을 검사한다.",
        instructions=(
            "컴파일·실행 가능성, 테스트 우회, 하드코딩, 회귀, 경계값, "
            "보안 위험과 과도한 변경을 검사하라."
        ),
        dependency="independent",
    ),
    ReviewerSpec(
        reviewer_id="math_reviewer",
        aspect="math",
        description="수학 계산·증명·조건 처리를 검사한다.",
        instructions=(
            "정의역, 필요·충분조건, 가짜해, 양화사, 경우 누락, "
            "대수적 동치성과 반례를 검사하라."
        ),
        dependency="dependent_core",
    ),
    ReviewerSpec(
        reviewer_id="physics_reviewer",
        aspect="physics",
        description="물리 법칙·차원·가정·극한을 검사한다.",
        instructions=(
            "차원 일관성, 보존 법칙, 근사 조건, 경계 조건, 극한과 "
            "수치 검산 가능성을 검사하라."
        ),
        dependency="independent",
    ),
    ReviewerSpec(
        reviewer_id="blindspot_reviewer",
        aspect="blindspot",
        description="다른 심사관이 관할하지 않은 빈 측면을 탐색한다.",
        instructions=(
            "이미 정의된 논리·범위·코드·수학·물리 외에 결론을 무너뜨릴 "
            "누락 측면이 있는지 탐색하라. 개인정보·동의·보안·권한 남용·"
            "법적/윤리적 위험처럼 후보의 채택 여부를 바꾸는 구체적 누락만 "
            "결함으로 판정하라. 결함 판정 전 반드시 후보 원문에서 그 결함을 "
            "입증하는 문구를 찾고, 그 문구가 실제 위험 또는 필수조건 누락을 "
            "보이는지 확인하라. 후보가 어떤 데이터를 수집·저장하지 않는다고 "
            "명시하면 그 선언을 사실로 전제하고, 가상의 임시 저장·로그·향후 "
            "수집 가능성을 만들어내지 마라. 이미 명시된 보호조치를 무시하거나 "
            "구현 세부사항이 더 많으면 좋겠다는 이유만으로 결함을 만들지 마라. "
            "예: 오프라인 미리보기이고 개인정보를 수집·저장하지 않으며 자동 "
            "판정·외부 공개도 없고 사람이 되돌릴 수 있다면, 반대 증거가 없는 한 "
            "pass_to_next_gate다. 결정을 바꾸는 누락을 후보 문구에 근거해 특정할 "
            "수 없으면 반드시 통과하라."
        ),
        dependency="independent",
    ),
]

DEFAULT_ACTIVE_REVIEWER_IDS = ["logic_reviewer", "scope_reviewer"]


class ReviewerRegistry:
    def __init__(self, reviewers: Iterable[ReviewerSpec] | None = None) -> None:
        self._reviewers: list[ReviewerSpec] = []
        self._by_id: dict[str, ReviewerSpec] = {}
        for reviewer in reviewers or DEFAULT_REVIEWERS:
            self.register(reviewer)

    def register(self, reviewer: ReviewerSpec) -> None:
        if reviewer.reviewer_id in self._by_id:
            raise ValueError(f"중복 reviewer_id: {reviewer.reviewer_id}")
        if not reviewer.aspect.strip():
            raise ValueError("reviewer aspect는 비어 있을 수 없습니다.")
        self._reviewers.append(reviewer)
        self._by_id[reviewer.reviewer_id] = reviewer

    def all(self) -> list[ReviewerSpec]:
        return list(self._reviewers)

    def select(self, reviewer_ids: list[str] | None = None) -> list[ReviewerSpec]:
        if not reviewer_ids:
            reviewer_ids = [
                item
                for item in DEFAULT_ACTIVE_REVIEWER_IDS
                if item in self._by_id
            ] or [item.reviewer_id for item in self._reviewers]
        unknown = [item for item in reviewer_ids if item not in self._by_id]
        if unknown:
            raise ValueError(f"알 수 없는 reviewer_id: {', '.join(unknown)}")
        requested = set(reviewer_ids)
        return [item for item in self._reviewers if item.reviewer_id in requested]
