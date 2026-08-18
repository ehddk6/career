from career_pipeline.behavior_span_parser_v2 import extract_behavior_spans

def pairs(text):
    return [(x.action, x.object) for x in extract_behavior_spans(text)]

def test_nominal_false_positives_are_suppressed():
    assert pairs("출석 확인 방식과 담당 역할을 정리함") == [("정리", "출석 확인 방식과 담당 역할")]
    assert pairs("기존 방식보다 처리 속도가 빨라짐") == []
    assert pairs("담당자와 동료가 실제 검토 업무에 사용함") == []
    assert pairs("장르별 분류가 이용자에게 직관적이지 않았고 안내 표시가 부족함") == []

def test_documentation_objects_keep_full_phrase_not_last_characters():
    assert pairs("행사별 필요 인원·역할에 맞춰 일정표 또는 배치안을 정리함") == [
        ("정리", "일정표 또는 배치안")
    ]
    assert pairs("급여자료 반복 확인 항목을 엑셀 정렬·필터·함수로 정리함") == [
        ("정리", "급여자료 반복 확인 항목")
    ]
    got = pairs("병원용·군의관용 안내 초안을 각각 작성하고 미확정 사항은 검토 요청함")
    assert got[0] == ("작성", "병원용·군의관용 안내 초안")
    assert not any(action == "검토" for action, _ in got)

def test_missing_documentation_action_memo_is_recovered():
    got = pairs("전화 문의를 메모하고 공통 질문별로 분류함")
    assert ("메모", "전화 문의") in got
    assert any(action == "분류" for action, _ in got)

def test_telegraphic_analysis_and_compound_action_survive():
    got = pairs("상인 인터뷰 & 타 시장 비교 분석 → 문제점 및 개선 방안 도출")
    assert any(action == "분석" for action, _ in got)
    assert any(action == "비교" for action, _ in got)

def test_coordinated_nominal_actions_are_bounded():
    got = pairs("증빙 대조와 지역 시세 확인")
    assert ("대조", "증빙") in got
    assert ("확인", "지역 시세") in got
    # A higher-order proposal must not be rewritten as executed reclassification.
    got2 = pairs("키워드·주제 중심 재분류와 안내 표시 추가를 제안함")
    assert not any(action == "분류" for action, _ in got2)


def test_requirement_and_passive_result_are_not_applicant_actions():
    assert pairs("과제(Task): 3000페이지 서류를 2일 내에 정리하고 대상자를 선별해야 함") == []
    assert pairs("조직 내 협업 문화가 개선되었습니다") == []
