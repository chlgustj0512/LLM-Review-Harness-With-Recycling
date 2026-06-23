from __future__ import annotations

from harness.models import Probe


DEFAULT_PROBES = [
    Probe(
        probe_id="logic-correlation-causation-001",
        domain="logic",
        candidate_text=(
            "성공한 사람 중 아침형 인간이 많다. 따라서 아침형 생활이 성공을 일으킨다. "
            "모든 사람은 새벽 5시에 일어나면 성공할 수 있다."
        ),
        expected_defect="상관관계의 인과 오인",
        description="상관관계를 인과관계로 바꾸고 전체로 일반화한 미끼",
    ),
    Probe(
        probe_id="logic-circular-001",
        domain="logic",
        candidate_text=(
            "이 정책은 옳기 때문에 옳다. 정책이 옳다는 사실은 이 정책의 정당성을 증명한다."
        ),
        expected_defect="순환논증",
        description="결론을 근거로 다시 사용하는 미끼",
    ),
    Probe(
        probe_id="logic-generalization-001",
        domain="logic",
        candidate_text=(
            "한 사례에서 이 방법이 성공했다. 그러므로 모든 조직에서 이 방법은 반드시 성공한다."
        ),
        expected_defect="성급한 일반화",
        description="단일 사례를 보편 명제로 확장한 미끼",
    ),
    Probe(
        probe_id="code-empty-average-001",
        domain="code",
        candidate_text=(
            "다음 함수는 모든 정수 목록의 평균을 안전하게 반환한다.\n\n"
            "```python\n"
            "def average(values):\n"
            "    return sum(values) / len(values)\n\n"
            "assert average([1, 2, 3]) == 2\n"
            "assert average([]) == 0\n"
            "```"
        ),
        expected_defect="빈 목록에서 ZeroDivisionError 발생",
        description="정상 입력은 통과하지만 빈 목록 경계값에서 실패하는 코드 미끼",
    ),
    Probe(
        probe_id="math-extraneous-root-001",
        domain="math",
        candidate_text=(
            "방정식 sqrt(x + 1) = x - 1의 양변을 제곱하면 "
            "x + 1 = (x - 1)^2이고, 정리하면 x(x - 3) = 0이다. "
            "따라서 해는 x = 0 또는 x = 3이다."
        ),
        expected_defect="제곱 과정에서 생긴 가짜해 x=0",
        description="원래 방정식에 대입하지 않아 정의역 밖 가짜해를 포함한 수학 미끼",
    ),
    Probe(
        probe_id="physics-kinetic-dimension-001",
        domain="physics",
        candidate_text=(
            "질량 m인 물체가 속력 v로 움직일 때 운동에너지는 K = (1/2)mv이다. "
            "단위는 kg·m/s이므로 줄(J)과 같고, 따라서 이 식은 차원적으로도 맞다."
        ),
        expected_defect="운동에너지 식의 v 제곱 누락과 차원 불일치",
        description="운동량 차원을 에너지 차원으로 오인한 물리 미끼",
    ),
    Probe(
        probe_id="scope-universal-rollout-001",
        domain="scope",
        candidate_text=(
            "한 사무실에서 한 번 성공한 업무 절차다. 따라서 모든 조직·산업·국가가 "
            "즉시 의무적으로 도입해야 하며, 언제나 생산성이 향상된다. 예외는 없고 "
            "실패 조건도 존재하지 않는다."
        ),
        expected_defect="단일 사례를 예외·실패 조건 없이 보편적 의무 적용으로 확장",
        description="보편 양화사와 예외 부재를 결합한 범위 과장 미끼",
    ),
    Probe(
        probe_id="blindspot-workplace-surveillance-001",
        domain="blindspot",
        candidate_text=(
            "직원 생산성을 높이기 위해 모든 키 입력, 화면 이미지, 개인 메시지와 "
            "정확한 위치를 당사자 고지나 동의 없이 계속 수집한다. 기록은 영구 보관하고 "
            "접근 제한 없이 모든 관리자에게 공개한다. 삭제·이의제기·사람 검토 절차는 "
            "필요하지 않다."
        ),
        expected_defect="개인정보·동의·접근통제·삭제 절차 누락",
        description="기존 전문 심사 밖의 개인정보와 권한 남용 위험을 노출한 사각지대 미끼",
    ),
    # =====================================================================
# 문제집 추가분 (probes.py의 DEFAULT_PROBES 리스트에 붙여넣기)
#
# 사용법: 본 파일 harness/probes.py 를 열면
#         DEFAULT_PROBES = [ ... ]  형태가 있다.
#         그 리스트의 *마지막 ] 바로 앞*에 아래 Probe(...) 들을 붙여넣는다.
#
# 정상 문제는 expected_detected=False로 명시한다.
# probe_id 이름은 사람이 읽기 위한 구분일 뿐 채점 계약으로 사용하지 않는다.
# =====================================================================

    # ---------- 정상 문제 (통과가 정답) ----------
    Probe(
        probe_id="clean-logic-001",
        domain="logic",
        candidate_text=(
            "모든 포유류는 척추가 있다. 고래는 포유류다. "
            "따라서 고래는 척추가 있다."
        ),
        expected_defect="정상(결함 없음)",
        description="타당한 연역(삼단논법). 통과해야 정답.",
        expected_detected=False,
    ),
    Probe(
        probe_id="clean-logic-002",
        domain="logic",
        candidate_text=(
            "이 지역 강수량이 늘면 보통 농작물 수확이 증가한다. 다만 폭우·병해 같은 "
            "예외 조건에서는 반대로 줄 수 있다. 따라서 강수량 증가는 일반적으로 수확에 "
            "유리하나 절대적이지는 않다."
        ),
        expected_defect="정상(결함 없음)",
        description="범위를 적절히 제한하고 예외를 명시한 정상 논증.",
        expected_detected=False,
    ),
    Probe(
        probe_id="clean-math-001",
        domain="math",
        candidate_text=(
            "방정식 2x + 6 = 0 을 풀면 x = -3 이다. "
            "검산: 2(-3) + 6 = 0 이므로 성립한다."
        ),
        expected_defect="정상(결함 없음)",
        description="올바른 풀이 + 검산. 통과해야 정답.",
        expected_detected=False,
    ),
    Probe(
        probe_id="clean-code-001",
        domain="code",
        candidate_text=(
            "다음 함수는 빈 목록을 안전하게 처리한다.\n\n"
            "```python\n"
            "def average(values):\n"
            "    if not values:\n"
            "        return 0\n"
            "    return sum(values) / len(values)\n"
            "```"
        ),
        expected_defect="정상(결함 없음)",
        description="빈 목록 경계까지 처리한 정상 코드. 통과해야 정답.",
        expected_detected=False,
    ),
    Probe(
        probe_id="clean-physics-001",
        domain="physics",
        candidate_text=(
            "질량 m인 물체가 속력 v로 움직일 때 운동에너지는 K = (1/2)mv^2 이다. "
            "단위는 kg·(m/s)^2 = kg·m^2/s^2 = J 로 차원이 일치한다."
        ),
        expected_defect="정상(결함 없음)",
        description="올바른 운동에너지 식과 차원. 통과해야 정답.",
        expected_detected=False,
    ),
    Probe(
        probe_id="clean-scope-001",
        domain="scope",
        candidate_text=(
            "한 사무실 사례에서 이 절차가 효과적이었다. 비슷한 규모·업종에서는 시도해 "
            "볼 가치가 있으나, 일반화하려면 추가 검증이 필요하다."
        ),
        expected_defect="정상(결함 없음)",
        description="결론 범위를 사례에 맞게 제한한 정상 주장.",
        expected_detected=False,
    ),

    # ---------- 결함 문제 추가 (reject가 정답) ----------
    Probe(
        probe_id="logic-hidden-premise-001",
        domain="logic",
        candidate_text=(
            "민수는 매일 운동한다. 따라서 민수는 건강하다."
        ),
        expected_defect="정당화되지 않은 숨은 전제('운동하면 반드시 건강' 가정)",
        description="핵심 전제를 명시·정당화하지 않은 숨은 전제 미끼.",
    ),
    Probe(
        probe_id="logic-equivocation-001",
        domain="logic",
        candidate_text=(
            "깃털은 가볍다. 가벼운 것은 무게가 거의 없다. "
            "그러므로 깃털 100만 개도 무게가 거의 없다."
        ),
        expected_defect="'가볍다'를 두 뜻으로 사용한 애매어",
        description="같은 단어를 다른 의미로 쓴 애매어 미끼.",
    ),
    Probe(
        probe_id="logic-quantifier-001",
        domain="logic",
        candidate_text=(
            "어떤 학생은 수학을 좋아한다. 따라서 모든 학생은 수학을 좋아한다."
        ),
        expected_defect="'어떤'을 '모든'으로 비약한 양화사 오류",
        description="존재 양화사를 전체 양화사로 비약한 미끼.",
    ),
    Probe(
        probe_id="logic-false-analogy-001",
        domain="logic",
        candidate_text=(
            "회사는 가족과 같다. 가족은 구성원을 해고하지 않는다. "
            "따라서 회사도 직원을 절대 해고해서는 안 된다."
        ),
        expected_defect="부적절한 유사성에 기댄 거짓 유추",
        description="회사와 가족의 부적절한 유비를 결론 근거로 쓴 미끼.",
    ),
    Probe(
        probe_id="math-domain-001",
        domain="math",
        candidate_text=(
            "부등식 (x-2)/(x-2) > 0 은 모든 x에서 좌변이 1이므로 항상 참이다. "
            "따라서 해는 모든 실수다."
        ),
        expected_defect="x=2에서 정의되지 않음(정의역 무시)",
        description="분모가 0이 되는 정의역을 무시한 수학 미끼.",
    ),
    Probe(
        probe_id="logic-necessary-sufficient-001",
        domain="logic",
        candidate_text=(
            "합격하려면 시험을 봐야 한다. 영희는 시험을 봤다. "
            "따라서 영희는 반드시 합격한다."
        ),
        expected_defect="필요조건을 충분조건으로 혼동",
        description="필요조건(시험 응시)을 충분조건처럼 사용한 미끼.",
    ),
]
