from dataclasses import replace
import json
from pathlib import Path
import re

from docx import Document

from career_pipeline.argument_search import PROOF_KINDS, SEMANTIC_DIMENSIONS
from career_pipeline.extractors import extract_path
from career_pipeline.golden_path import (
    GoldenPathConfig,
    advance_golden_path,
    start_golden_path,
)
from career_pipeline.golden_path_converged import converged_services
from career_pipeline.inventory import digest_path
from career_pipeline.models import SourceRecord
from career_pipeline.profile_builder import build_proposed_ledger
from career_pipeline.profile_schema import ClaimVerification, ledger_to_dict
from career_pipeline.research_workspace import initialize_research_workspace


QUESTION = "테스트공사 행정 직무에 지원한 동기를 구체적으로 기술해 주십시오."


def _write_docx(path: Path, *paragraphs: str) -> Path:
    document = Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)
    return path


def _build_confirmed_profile(root: Path) -> Path:
    source_path = root / "career.txt"
    source_path.write_text(
        "신청 서류를 검토해 누락 원인을 분류하고, 고객 보완 안내가 필요한 항목은 "
        "담당자에게 근거와 함께 보고했습니다.",
        encoding="utf-8",
    )
    source = SourceRecord(
        source_path,
        "career.txt",
        ".txt",
        source_path.stat().st_size,
        digest_path(source_path),
        "use",
    )
    proposed = build_proposed_ledger(root, [extract_path(source)])
    confirmed_experiences = tuple(
        replace(
            experience,
            claims=tuple(
                replace(
                    claim,
                    status="confirmed",
                    verification=ClaimVerification(
                        method="documented_total",
                        measurement_period="fixture",
                        scope="fixture source sentence",
                        contribution="contributed",
                    ),
                )
                for claim in experience.claims
            ),
            status="confirmed",
            confirmed_at="2026-08-17T12:00:00+09:00",
        )
        for experience in proposed.experiences
    )
    confirmed = replace(proposed, experiences=confirmed_experiences)
    profile_dir = root / ".career_profile"
    profile_dir.mkdir()
    profile = profile_dir / "experience_ledger.json"
    profile.write_text(
        json.dumps(ledger_to_dict(confirmed), ensure_ascii=False),
        encoding="utf-8",
    )
    return profile


def _json_tail(prompt: str, marker: str) -> dict:
    start = prompt.rfind(marker)
    assert start >= 0, f"missing prompt marker {marker!r}"
    return json.loads(prompt[start:])


def _tag_json(prompt: str, tag: str) -> dict:
    start_marker = f"<{tag}>\n"
    end_marker = f"\n</{tag}>"
    start = prompt.index(start_marker) + len(start_marker)
    end = prompt.index(end_marker, start)
    return json.loads(prompt[start:end])


def _answer_for(blueprint: dict, *, alternate: bool) -> tuple[str, list[str], list[str]]:
    experience = blueprint.get("experience") or {}
    claims = [
        row
        for row in experience.get("selected_claims", []) or []
        if isinstance(row, dict) and row.get("claim_id")
    ]
    research = [
        row
        for row in blueprint.get("research_claims", []) or []
        if isinstance(row, dict) and row.get("claim_id")
    ]
    assert claims
    assert research

    answer = (
        "테스트공사가 지원 신청 자료를 검토해 적격 여부를 확인하고, 행정 담당자가 신청 서류를 "
        "검토해 고객에게 보완 사항을 안내하는 역할에 매력을 느껴 지원했습니다. "
        "저는 신청 서류를 검토해 누락을 구분하고 근거를 남기는 방식이 정확한 행정의 "
        "출발점이라고 생각합니다. 이전 업무에서도 신청 서류를 검토해 누락 원인을 분류하고, "
        "고객 보완 안내가 필요한 항목은 담당자에게 근거와 함께 보고했습니다. "
        "신청 서류를 검토하면서 누락과 보완 안내를 구분해 근거를 남겨야 정확한 안내가 "
        "가능하다는 점을 배웠습니다. 입사 후에는 먼저 공고와 업무 기준을 읽고 신청 서류의 누락과 "
        "불일치를 구분해 검토하겠습니다. 초기에는 선배의 판단과 제 검토 기록을 대조해 기준을 "
        "익히고, 권한 밖의 사항은 단정하지 않고 근거를 붙여 질문하겠습니다. 반복되는 보완 사유는 "
        "항목별로 정리해 고객 안내에서 빠뜨리는 내용이 없도록 하되, 기준 변경이 확인되면 기존 정리보다 "
        "최신 공식 기준을 우선하겠습니다. 이렇게 사실 확인, 예외 구분, 근거 있는 안내를 한 흐름으로 "
        "연결해 테스트공사의 신청 검토 업무에서 정확성과 설명 가능성을 함께 높이겠습니다."
    )
    if alternate:
        answer = answer.replace(
            "역할에 매력을 느껴 지원했습니다.",
            "역할이 제 업무 방식과 맞는다고 판단해 지원했습니다.",
        )
    assert 480 <= len(answer) <= 600

    return (
        answer,
        [str(row["claim_id"]) for row in claims],
        [str(row["claim_id"]) for row in research],
    )


class DeterministicModelRunner:
    def __init__(self):
        self.calls: list[str] = []

    def __call__(self, stage: str, prompt: str, model_id: str, timeout_ms: int):
        self.calls.append(stage)

        if stage.startswith("deep_route_plan"):
            data = _json_tail(prompt, '{"blueprint"')
            blueprint = data["blueprint"]
            support = [row["ref"] for row in data["story_kernel"]["support"]]
            assert support
            count = int(re.search(r"Create exactly (\d+)", prompt).group(1))
            routes = []
            for index in range(1, count + 1):
                routes.append(
                    {
                        "route_id": f"q{blueprint['question_index']}-r{index}",
                        "argument_posture": f"fixture-posture-{index}",
                        "thesis": f"검증된 경험과 공식 근거를 연결하는 경로 {index}",
                        "thesis_support_refs": support,
                        "proof_chain": [
                            {
                                "kind": kind,
                                "text": f"{kind} 근거를 승인된 자료에서만 사용한다.",
                                "support_refs": support,
                            }
                            for kind in PROOF_KINDS
                        ],
                        "closing_move": "검증된 업무 방식과 지원 직무를 연결한다.",
                        "evidence_gaps": [],
                        "distinctive_anchor_refs": support[:1],
                    }
                )
            return {
                "blueprint_id": blueprint["blueprint_id"],
                "question_index": blueprint["question_index"],
                "routes": routes,
            }

        if stage.startswith("deep_route_judge"):
            data = _json_tail(prompt, '{"question"')
            ids = [str(row["route_id"]) for row in data["routes"]]
            preferred = min(ids)
            return {
                "routes": [
                    {
                        "route_id": route_id,
                        "scores": {
                            dimension: 4 if route_id == preferred else 3
                            for dimension in SEMANTIC_DIMENSIONS
                        },
                        "fatal_issue": False,
                    }
                    for route_id in ids
                ]
            }

        if stage.startswith("deep_prose_generate"):
            data = _json_tail(prompt, '{"blueprint"')
            blueprint = data["blueprint"]
            alternate = stage.endswith("_2")
            answer, claim_ids, research_ids = _answer_for(
                blueprint,
                alternate=alternate,
            )
            return {
                "blueprint_id": blueprint["blueprint_id"],
                "question_index": blueprint["question_index"],
                "answer": answer,
                "used_claim_ids": claim_ids,
                "used_research_ids": research_ids,
            }

        if stage.startswith("deep_prose_judge"):
            data = _json_tail(prompt, '{"question"')
            ids = [str(row["route_id"]) for row in data["routes"]]
            preferred = min(ids)
            return {
                "routes": [
                    {
                        "route_id": route_id,
                        "scores": {
                            dimension: 4 if route_id == preferred else 3
                            for dimension in SEMANTIC_DIMENSIONS
                        },
                        "fatal_issue": False,
                    }
                    for route_id in ids
                ]
            }

        if stage.startswith("nrs_production_generate"):
            facts = _tag_json(prompt, "allowed_facts")
            contract = _tag_json(prompt, "output_contract")
            claim_ids = [str(row["claim_id"]) for row in facts["allowed_claims"]]
            research_ids = [str(row["claim_id"]) for row in facts["allowed_research"]]
            answer = (
                "테스트공사는 지원 신청 자료를 검토해 적격 여부를 판단하고, 행정 담당자는 고객에게 보완 사항을 안내합니다. "
                "이 업무는 작은 누락을 초기에 발견해 신청자가 다음 절차로 나아가도록 돕는 일이라고 생각해 지원했습니다. "
                "이전 업무에서 저는 신청 서류를 검토하며 누락 원인을 분류하고, 보완 안내가 필요한 항목은 근거를 정리해 담당자에게 보고했습니다. "
                "그 과정에서 빠른 처리만을 앞세우기보다 어떤 정보가 부족한지 분명히 구분해야 안내가 흔들리지 않는다는 점을 배웠습니다. "
                "입사 후에는 공고와 업무 기준을 숙지한 뒤 신청 서류를 꼼꼼히 살피고, 예외 사항은 담당자와 협의해 정확한 보완 안내로 연결하겠습니다. "
                "또한 검토 기록을 남겨 앞선 처리의 맥락을 살피고, 같은 문의가 이어져도 일관된 기준으로 응대하겠습니다. "
                "반복되는 보완 사유는 항목별로 정리해 고객이 필요한 내용을 제때 알 수 있도록 돕겠습니다. "
                "이를 통해 고객이 다음 행동을 스스로 준비할 수 있도록 돕겠습니다."
            )
            if stage.endswith("_2"):
                answer = answer.replace("초기에 발견해", "미리 살펴")
            elif stage.endswith("_3"):
                answer = answer.replace("일관된 기준으로 응대하겠습니다.", "일관된 기준으로 안내하겠습니다.")
            assert 480 <= len(answer) <= 600
            return {
                "blueprint_id": contract["blueprint_id"],
                "question_index": contract["question_index"],
                "answer": answer,
                "used_claim_ids": claim_ids,
                "used_research_ids": research_ids,
            }

        if stage.startswith("nrs_production_candidate_select"):
            candidate_ids = list(dict.fromkeys(re.findall(r'"candidate_id"\s*:\s*"([^"]+)"', prompt)))
            return {"ranking": [
                {"candidate_id": candidate_id, "rank": index}
                for index, candidate_id in enumerate(sorted(candidate_ids), start=1)
            ]}

        if stage.startswith("deep_portfolio_critic"):
            return {"issues": []}

        raise AssertionError(f"unexpected model stage: {stage}")


def _write_research(run: Path) -> None:
    claims = [
        {
            "claim_id": "research-org-role",
            "claim": "테스트공사는 지원 신청 자료를 검토해 적격 여부를 확인한다.",
            "source_url": "https://official.example.go.kr/about/role",
            "checked_at": "2026-08-17",
            "evidence_excerpt": "지원 신청 자료를 검토하여 적격 여부를 확인하는 업무를 수행한다.",
            "source_type": "official_program_page",
            "published_at": "2026-08-01",
            "basis_date": "2026-08-01",
            "verification_status": "confirmed",
            "claim_type": "organization_role",
            "application_use": "문항 1의 지원 동기 근거로 활용",
            "argument_role": "organization_differentiator",
            "source_tier": 1,
            "support_strength": "direct",
            "freshness_class": "stable",
            "submission_authority": True,
        },
        {
            "claim_id": "research-job-duty",
            "claim": "행정 담당자는 신청 서류를 검토하고 고객에게 보완 사항을 안내한다.",
            "source_url": "https://official.example.go.kr/jobs/admin",
            "checked_at": "2026-08-17",
            "evidence_excerpt": "신청 서류 검토와 고객 보완 안내를 담당 업무로 명시한다.",
            "source_type": "official_program_page",
            "published_at": "2026-08-10",
            "basis_date": "2026-08-10",
            "verification_status": "confirmed",
            "claim_type": "job_duty",
            "application_use": "문항 1의 직무 역할 근거로 활용",
            "argument_role": "real_operating_role",
            "source_tier": 1,
            "support_strength": "direct",
            "freshness_class": "current",
            "submission_authority": True,
        },
    ]
    (run / "04_공식근거.json").write_text(
        json.dumps(claims, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    execution = {
        "policy": "evidence-first",
        "skill_name": "deterministic-synthetic-acceptance-fixture",
        "mode": "ordinary-online",
        "searched_at": "2026-08-17T12:00:00+09:00",
        "status": "verified",
        "queries": ["테스트공사 공식 역할", "테스트공사 행정 직무"],
        "source_families": ["official-primary"],
        "verified_claim_ids": [row["claim_id"] for row in claims],
    }
    (run / "04_리서치실행.json").write_text(
        json.dumps(execution, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    report = initialize_research_workspace(run)
    assert report["coverage"]["stop_research"] is True


def _write_interview_pack(run: Path, response: dict) -> None:
    answer = str(response["answer"])
    evidence_ids = [
        str(row.get("experience_id"))
        for row in response.get("experience_refs", [])
        if isinstance(row, dict) and row.get("experience_id")
    ] + [str(value) for value in response.get("research_refs", [])]
    sentences = [item.strip() for item in answer.split(".") if item.strip()]
    short = ". ".join(sentences[:2]) + "."
    medium = ". ".join(sentences[:4]) + "."
    long = ". ".join(sentences[:6]) + "."
    pack = f"""# 면접대비팩

## 1분 자기소개
{medium}

## 문항 1 대응
- 30초 답변: {short}
- 60초 답변: {medium}
- 90초 답변: {long}
- 꼬리질문: 신청 서류 검토에서 가장 먼저 확인할 기준은 무엇입니까?
- 꼬리답변: 공고와 공식 업무 기준을 먼저 확인하고, 누락과 불일치를 구분한 뒤 권한 밖의 사항은 근거와 함께 질문하겠습니다.
- 압박질문: 빠른 처리와 정확성이 충돌하면 무엇을 우선하겠습니까?
- 압박답변: 임의로 단정하지 않고 필수 기준을 먼저 확인한 뒤, 예외는 담당자에게 근거와 함께 보고해 처리 속도와 정확성을 함께 관리하겠습니다.
- 평가 기준: 근거 기반 판단, 직무 이해, 권한 경계, 설명 가능성
- 근거: {', '.join(evidence_ids)}
"""
    (run / "08_면접대비팩.md").write_text(pack, encoding="utf-8")


def test_converged_golden_path_reaches_complete_with_deterministic_model_boundary(
    tmp_path: Path,
):
    workspace = tmp_path / "private-career-workspace"
    workspace.mkdir()
    profile = _build_confirmed_profile(workspace)

    posting = _write_docx(
        workspace / "posting.docx",
        "기관명",
        "테스트공사",
        "채용분야",
        "행정",
        "담당업무",
        "신청 서류 검토 및 고객 보완 안내",
        "필요역량",
        "정확성",
        "자기소개서",
        QUESTION,
        "0/600 (글자 수, 공백 포함)",
    )
    draft = _write_docx(
        workspace / "draft.docx",
        QUESTION,
        "0/600 (글자 수, 공백 포함)",
    )

    state = start_golden_path(
        root=workspace,
        target="테스트공사 행정",
        draft=draft,
        posting=str(posting),
        profile=profile,
        run_name="synthetic-converged-e2e",
        official_domains=("official.example.go.kr",),
        official_source=True,
    )
    assert state["status"] == "waiting_for_research"
    run = Path(state["run_dir"])
    _write_research(run)
    (run / "05_문항전략.md").write_text("# 문항전략", encoding="utf-8")

    model_runner = DeterministicModelRunner()
    services = converged_services(model_runner=model_runner)
    config = GoldenPathConfig(
        writer_model_id="synthetic-model",
        judge_model_ids=("synthetic-model",),
        route_count=2,
        prose_realisations=2,
        postprocess="never",
        reuse_cache=True,
    )

    first = advance_golden_path(run, config=config, services=services)
    assert first["status"] == "waiting_for_interview_pack"
    assert model_runner.calls
    assert (run / "05_근거포트폴리오.json").is_file()
    assert (run / "05_NRS_서사선택.json").is_file()

    draft_payload = json.loads((run / "draft.json").read_text(encoding="utf-8"))
    _write_interview_pack(run, draft_payload[0])

    second = advance_golden_path(run, config=config, services=services)
    assert second["status"] == "complete"

    for name in (
        "05_근거포트폴리오.json",
        "05_NRS_서사선택.json",
        "12_주장컴파일.json",
        "08_면접지능설계.json",
        "11_최종품질감사.json",
        "13_골든패스.json",
    ):
        assert (run / name).is_file(), name

    before = list(model_runner.calls)
    third = advance_golden_path(run, config=config, services=services)
    assert third["status"] == "complete"
    assert model_runner.calls == before
