---
run_id: CR-20260715-1539
company_data_package_id: CR-DATA-001
company_data_package_version: "1.0"
step: STEP_1
step_status: COMPLETED_WITH_GAPS
frozen_at: 2026-07-15T16:00:22+09:00
---

# INPUT INVENTORY

## 1. 범위 요약

- 허용된 로컬 범위: `input/`만 사용
- 로컬 파일: 62개
- 기존 원장에서 추출한 외부 URL 후보: 4개(이번 단계 미접속)
- 통합 source record: 66개
- 내용이 정확히 동일한 중복 파생 파일: 4개
- 누락된 경험원장 상위 원문: 2개, 영향 claim 13개
- 입력 스냅샷 SHA-256: `ba71a9931e821184bbb932a5a9c1dd12c48cef0a145db79d9729902ab35d7ca2`

## 2. 분류 결과

| source_class | 파일 수 | 사용 규칙 |
|---|---:|---|
| `APPLICANT_SOURCE` | 1 | 지원자 bridge 전용. 수치·성과는 claim 단위 검증. |
| `APPLICATION_OUTPUT` | 5 | 파생 산출물. 사실 근거로 사용하지 않음. |
| `APPROVED_APPLICANT_LEDGER` | 1 | 지원자 bridge 전용. 상위 원문 누락 claim은 보류. |
| `DERIVED_APPLICANT_ANALYSIS` | 2 | 파생 산출물. 사실 근거로 사용하지 않음. |
| `DERIVED_RESEARCH_LEDGER` | 1 | URL 발견용. 기존 verified 상태 자동 승계 금지. |
| `DERIVED_RESEARCH_OUTPUT` | 2 | 파생 산출물. 사실 근거로 사용하지 않음. |
| `DERIVED_STRUCTURED_EXTRACTION` | 2 | 원문 추적 보조만 허용. |
| `DERIVED_WORKSPACE_INVENTORY` | 1 | 파생 산출물. 사실 근거로 사용하지 않음. |
| `DISPLAY_DERIVATIVE` | 8 | 파생 산출물. 사실 근거로 사용하지 않음. |
| `LOCAL_PRIMARY_SNAPSHOT` | 1 | 핵심 로컬 근거. 단, 전체 공식 공고와 현재성은 재검증. |
| `METHODOLOGY_GUIDANCE` | 2 | 파생 산출물. 사실 근거로 사용하지 않음. |
| `MODEL_EVALUATION_DERIVATIVE` | 6 | 파생 산출물. 사실 근거로 사용하지 않음. |
| `MODEL_GENERATED_DERIVATIVE` | 8 | 파생 산출물. 사실 근거로 사용하지 않음. |
| `OUT_OF_SCOPE_OFFICIAL_DOCUMENT` | 6 | 엔터티 불일치로 제외. |
| `PII_IMAGE` | 1 | 직접 개인정보. 사용 금지. |
| `PIPELINE_METADATA` | 15 | 파생 산출물. 사실 근거로 사용하지 않음. |

## 3. 핵심 입력과 계보 판단

1. `input/career_run/00_채용공고원문/source.docx`는 기관명·채용분야·담당업무·자기소개서 문항을 직접 담고 있으며 SHA-256은 `5b6f69118ca1eece39f284fb26c18e42422ba01088f978b9829c0501bc456779`이다. 다만 전체 채용공고가 아닌 축약 스냅샷이므로 일정·자격·근무조건은 확정할 수 없다.
2. `input/career_run/02_확정경험원장.json`은 20개 경험 claim을 `confirmed`로 기록한다. 그중 7개는 현재 포함된 `input/경험정리/경험정리.docx`와 SHA-256이 일치한다.
3. 나머지 13개 claim은 `경험정리/경험요약정리.docx`와 `경험정리/인생기술서.docx`를 참조하지만 두 파일은 현재 `input/`에 없다. 승인 원장의 값은 보존하되 이번 패키지에서 독립 재검증되었다고 표시하지 않는다.
4. `input/career_run/04_공식근거.json`의 5개 claim은 2026-07-13 기존 실행의 결과다. 이번 STEP 1에서는 외부 접속을 하지 않았으므로 4개 고유 URL을 모두 `NEEDS_REVERIFICATION`으로 등록했다.
5. `input/career_run/01_자료목록.md`는 현재 패키지 밖의 다수 경로를 나열하는 과거 카탈로그다. 그 안의 파일명만으로 파일 존재·내용·해시를 인정하지 않는다.

## 4. 제외·주의 항목

- 한국도로공사서비스 직무기술서 PDF 6개: 대상 법인 불일치, `EXCLUDED_ENTITY_MISMATCH`
- 지원자 증명사진 1개: 직접 개인정보, `PROHIBITED_FOR_COMPANY_RESEARCH`
- 자기소개서·면접팩·모델 후보·심사 결과·렌더링: claim 발견과 실행 계보 확인에만 사용
- `draft_final.json`/`rigorous/selected.json` 및 세 심사자 raw/정규화 쌍: 각각 내용이 동일한 중복

## 5. 외부 URL 출처 후보

| Source ID | 제목 | 발행·운영 주체 | 기존 확인일 | 기존 게시일 | 상태 | URL |
|---|---|---|---|---|---|---|
| URL-001 | 2026년 하반기 체험형 청년인턴 채용공고·접수 페이지 | 신용보증기금 채용접수 페이지(운영 법인 미확인) | 2026-07-13 | 2026-07-09 | `NEEDS_REVERIFICATION` | https://kodit2.saramin.co.kr/service/kodit2/3872/applicant/apply/recruit_default.asp |
| URL-002 | 환율·중소기업 한시 특별지원 관련 공식 자료 | 한국은행 | 2026-07-13 | 2026-03-12 | `NEEDS_REVERIFICATION` | https://www.bok.or.kr/portal/bbs/B0000156/view.do?depth=200067&menuNo=200067&nttId=10096935&programType=newsData&relate=Y |
| URL-003 | 신용보증제도 개요 | 신용보증기금 | 2026-07-13 | UNVERIFIED | `NEEDS_REVERIFICATION` | https://www.kodit.co.kr/kodit/cm/cntnts/cntntsView.do?cntntsId=11064&mi=2521 |
| URL-004 | 지역 수출기업 협약보증 관련 공식 자료 | 신용보증기금 | 2026-07-13 | 2026-03-24 | `NEEDS_REVERIFICATION` | https://www.kodit.co.kr/kodit/na/ntt/selectNttInfo.do?bbsId=47&mi=2639&nttSn=4429533 |

## 6. 전체 로컬 파일

전체 SHA-256과 기계 판독 필드는 `manifest.json`에도 동일하게 기록한다.

| Source ID | 경로 | source_class | 역할 | 엔터티 범위 | 사용성 | 검증 상태 | 중복 원본 | SHA-256 |
|---|---|---|---|---|---|---|---|---|
| LOC-001 | `input/career_run/00_채용공고분석.json` | `DERIVED_STRUCTURED_EXTRACTION` | `POSTING_EXTRACTION` | 신용보증기금 | `SUPPORTING_TRACE_ONLY` | `TRACEABLE_TO_LOCAL_SNAPSHOT` | - | `ba3bcd6961bc22ff875d537399004b7d6f9e305dacffb533d0944617eac05d3b` |
| LOC-002 | `input/career_run/00_채용공고분석.md` | `DERIVED_STRUCTURED_EXTRACTION` | `POSTING_EXTRACTION` | 신용보증기금 | `SUPPORTING_TRACE_ONLY` | `TRACEABLE_TO_LOCAL_SNAPSHOT` | - | `85aa9f620e96c408b24a6a340448c8a1a3ba0ee365acefadce2136f776138480` |
| LOC-003 | `input/career_run/00_채용공고원문/source.docx` | `LOCAL_PRIMARY_SNAPSHOT` | `JOB_POSTING_EXCERPT` | 신용보증기금 | `CORE_LOCAL_EVIDENCE` | `USER_ATTESTED_NEEDS_REVERIFICATION` | - | `5b6f69118ca1eece39f284fb26c18e42422ba01088f978b9829c0501bc456779` |
| LOC-004 | `input/career_run/01_자료목록.md` | `DERIVED_WORKSPACE_INVENTORY` | `HISTORICAL_FILE_CATALOG` | 다수 기관·지원자 자료 | `CATALOG_ONLY` | `REFERENCED_FILES_NOT_PRESENT` | - | `75a427a9be3fdbf0bedd3f07578624ce4754fb625e63a164a211b982503a7f59` |
| LOC-005 | `input/career_run/02_확정경험원장.json` | `APPROVED_APPLICANT_LEDGER` | `APPLICANT_CLAIM_LEDGER` | 지원자 | `APPLICANT_EVIDENCE_WITH_LINEAGE_GAPS` | `PARTIAL_LOCAL_LINEAGE` | - | `485c2fad17ec5cddf117b884e0baf61d4aa9bcfdc9c5b1cc96ab1435e2d3f2c4` |
| LOC-006 | `input/career_run/03_경험직무매칭.json` | `DERIVED_APPLICANT_ANALYSIS` | `EXPERIENCE_JOB_MATCHING` | 지원자·신용보증기금 | `HYPOTHESIS_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `f3fa46c805196366e87b6af4315cd92997bd0e420d1e85e2ff0c8c8ef0246061` |
| LOC-007 | `input/career_run/03_경험직무매칭.md` | `DERIVED_APPLICANT_ANALYSIS` | `EXPERIENCE_JOB_MATCHING` | 지원자·신용보증기금 | `HYPOTHESIS_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `8db5eb0f2ed59d0cde56272e2061d5e6116d436651b8ad6a1e5cf87daf9135a3` |
| LOC-008 | `input/career_run/04_공식근거.json` | `DERIVED_RESEARCH_LEDGER` | `EXTERNAL_SOURCE_LEADS` | 신용보증기금·한국은행 | `SOURCE_DISCOVERY_LEADS_ONLY` | `NEEDS_REVERIFICATION` | - | `4956a70618e06435f17e122eaa31fd1cb33abe00df425fd468302df46b88bcf0` |
| LOC-009 | `input/career_run/04_기업직무조사.md` | `DERIVED_RESEARCH_OUTPUT` | `PRIOR_COMPANY_RESEARCH` | 신용보증기금·한국은행 | `HYPOTHESIS_AND_SOURCE_DISCOVERY_ONLY` | `NEEDS_REVERIFICATION` | - | `c7046db516f3cb2f2a659b79d3cdaee4ce843ebe2afdc33557207dc60aaafe54` |
| LOC-010 | `input/career_run/04_리서치실행.json` | `DERIVED_RESEARCH_OUTPUT` | `PRIOR_COMPANY_RESEARCH` | 신용보증기금·한국은행 | `HYPOTHESIS_AND_SOURCE_DISCOVERY_ONLY` | `NEEDS_REVERIFICATION` | - | `21bea36e9de3893045b614ec7626e894c51080bf42f7041075f5024fcb9e9450` |
| LOC-011 | `input/career_run/05_문항전략.md` | `METHODOLOGY_GUIDANCE` | `WRITING_STRATEGY` | 지원서 작성 프레임 | `METHOD_ONLY` | `NOT_FACT_EVIDENCE` | - | `38880080d04469ceee8a25744ac5a190ae96ef2797d995670dd4a2c7c4b642aa` |
| LOC-012 | `input/career_run/05_작성가이드_유튜브프레임.md` | `METHODOLOGY_GUIDANCE` | `WRITING_STRATEGY` | 지원서 작성 프레임 | `METHOD_ONLY` | `NOT_FACT_EVIDENCE` | - | `12d9f07df5ed449ff1e06f8d3beef43ac635fc5b3e729f018b65a26a05c72987` |
| LOC-013 | `input/career_run/06_자기소개서.docx` | `APPLICATION_OUTPUT` | `SELF_INTRODUCTION_OR_INTERVIEW_DRAFT` | 신용보증기금 지원서 | `CLAIM_DISCOVERY_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `fb267d56de4c9becd9bbcdb33207fcb60327b4268c163d41f5df9c141f3b46eb` |
| LOC-014 | `input/career_run/06_자기소개서.md` | `APPLICATION_OUTPUT` | `SELF_INTRODUCTION_OR_INTERVIEW_DRAFT` | 신용보증기금 지원서 | `CLAIM_DISCOVERY_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `92a0117dabdce2cfa1971f96c196c42b89a00aec20d49d10b49a4f6cef6536f0` |
| LOC-015 | `input/career_run/08_면접대비팩.md` | `APPLICATION_OUTPUT` | `SELF_INTRODUCTION_OR_INTERVIEW_DRAFT` | 신용보증기금 지원서 | `CLAIM_DISCOVERY_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `4e901dc22f7137616ff6be935a861704b6d8ae437b949e6df3eca3b0e1109068` |
| LOC-016 | `input/career_run/09_copyeditor_report.json` | `PIPELINE_METADATA` | `QUALITY_OR_RUN_AUDIT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `47c9585bbe34f399b26fa8babf3f3dad95c2430c6a0f25281729476dfbf389f2` |
| LOC-017 | `input/career_run/09_style_diagnostics.json` | `PIPELINE_METADATA` | `QUALITY_OR_RUN_AUDIT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `61b55f2b0a07d46f0345d6e16cc10dfadb1456a77c2998b19d895043af8459f9` |
| LOC-018 | `input/career_run/10_품질점수.json` | `PIPELINE_METADATA` | `QUALITY_OR_RUN_AUDIT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `6191e7036b07ca26905448a64f9e507386321288abfbd70d965be5b19c6caa1e` |
| LOC-019 | `input/career_run/11_최종품질감사.json` | `PIPELINE_METADATA` | `QUALITY_OR_RUN_AUDIT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `db55f368cb825bf72f93f65a318a5f719dddedfedd4abd1cf6dca6c6d95ed48a` |
| LOC-020 | `input/career_run/11_최종품질감사.md` | `PIPELINE_METADATA` | `QUALITY_OR_RUN_AUDIT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `bad5daf84252c35a275d4f74d594233aa0feb4c2be697c3c20e451a1b061ea1f` |
| LOC-021 | `input/career_run/12_최종산출물.json` | `PIPELINE_METADATA` | `QUALITY_OR_RUN_AUDIT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `32adf25c653e09d89ebf95fec255ce5f47922449d96c1659f277fe013cce9beb` |
| LOC-022 | `input/career_run/draft.json` | `APPLICATION_OUTPUT` | `SELF_INTRODUCTION_OR_INTERVIEW_DRAFT` | 신용보증기금 지원서 | `CLAIM_DISCOVERY_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `f228314386577909d8485eb5290483b3829d8a42e3d7ba4c18a15d5a74d0975b` |
| LOC-023 | `input/career_run/draft_final.json` | `APPLICATION_OUTPUT` | `SELF_INTRODUCTION_OR_INTERVIEW_DRAFT` | 신용보증기금 지원서 | `CLAIM_DISCOVERY_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `de94aed7e0cdaaf22607bd4afbf649d63e91861f18d3dc94c899b655590da50b` |
| LOC-024 | `input/career_run/rendered_docx_final/06_자기소개서.pdf` | `DISPLAY_DERIVATIVE` | `APPLICATION_RENDER` | 신용보증기금 지원서 | `VISUAL_QA_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `3487189c37aa88e119cf29d59c4a3e7906dad73538ab378c42347d28f9c14d27` |
| LOC-025 | `input/career_run/rendered_docx_final/page-1.jpg` | `DISPLAY_DERIVATIVE` | `APPLICATION_RENDER` | 신용보증기금 지원서 | `VISUAL_QA_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `783669cdb80e05cfc2845d1fc1de73fee9f206afbdb3a840562b575a8e18407b` |
| LOC-026 | `input/career_run/rendered_docx_final/page-2.jpg` | `DISPLAY_DERIVATIVE` | `APPLICATION_RENDER` | 신용보증기금 지원서 | `VISUAL_QA_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `e02e6d805f313626d89d3b759697b5a1784e6bb65cf98dae7b262de5c8eb2770` |
| LOC-027 | `input/career_run/rendered_docx_final/page-3.jpg` | `DISPLAY_DERIVATIVE` | `APPLICATION_RENDER` | 신용보증기금 지원서 | `VISUAL_QA_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `0a0ae2e0715de10f4010ed3aa9bdbc7b6d453002bd4acc75fb9deb9cb3a8e411` |
| LOC-028 | `input/career_run/rendered_docx/06_자기소개서.pdf` | `DISPLAY_DERIVATIVE` | `APPLICATION_RENDER` | 신용보증기금 지원서 | `VISUAL_QA_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `cca69196ff83bb0908aaac9687ba168537bac96d807f90072525923a8f205e28` |
| LOC-029 | `input/career_run/rendered_docx/page-1.png` | `DISPLAY_DERIVATIVE` | `APPLICATION_RENDER` | 신용보증기금 지원서 | `VISUAL_QA_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `0929f70f82bdefd536e201a2cfffd825eef6ae76c75c1db69c81f38bf4d10319` |
| LOC-030 | `input/career_run/rendered_docx/page-2.png` | `DISPLAY_DERIVATIVE` | `APPLICATION_RENDER` | 신용보증기금 지원서 | `VISUAL_QA_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `f2eeab3b40f03179fff896bda7a7a4b118b17689ec07102f59f986f746175ec3` |
| LOC-031 | `input/career_run/rendered_docx/page-3.png` | `DISPLAY_DERIVATIVE` | `APPLICATION_RENDER` | 신용보증기금 지원서 | `VISUAL_QA_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `cd0b88b595ef5448b04a5a417f4bcc4b11571bfccc8e0bb729bf19afd3c7bbf4` |
| LOC-032 | `input/career_run/rigorous/aggregate.json` | `PIPELINE_METADATA` | `RIGOROUS_SELECTION_LINEAGE` | 신용보증기금 지원서 | `PROCESS_LINEAGE_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `a0d6f6fcc66e772644003e7deaac11285a2a217e38344df53896f7b992d0cb6e` |
| LOC-033 | `input/career_run/rigorous/blind_candidates.json` | `PIPELINE_METADATA` | `RIGOROUS_SELECTION_LINEAGE` | 신용보증기금 지원서 | `PROCESS_LINEAGE_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `df0ee4085c429926872b67feec9d0ecd0e83af9605750347f8834955bad09524` |
| LOC-034 | `input/career_run/rigorous/candidates/generated_1.json` | `MODEL_GENERATED_DERIVATIVE` | `APPLICATION_CANDIDATE` | 신용보증기금 지원서 | `EXCLUDED_AS_EVIDENCE` | `MODEL_OUTPUT` | - | `91457deb88d5e275ce6aa7116573704864e1e25427f89c3951461e8b0cfdeae3` |
| LOC-035 | `input/career_run/rigorous/candidates/generated_1_raw.json` | `MODEL_GENERATED_DERIVATIVE` | `APPLICATION_CANDIDATE` | 신용보증기금 지원서 | `EXCLUDED_AS_EVIDENCE` | `MODEL_OUTPUT` | - | `5a3305fb807074fa61a18f6f5de1e4a36b03ef473d0dd88bc9876cf0a80d7a77` |
| LOC-036 | `input/career_run/rigorous/candidates/generated_2.json` | `MODEL_GENERATED_DERIVATIVE` | `APPLICATION_CANDIDATE` | 신용보증기금 지원서 | `EXCLUDED_AS_EVIDENCE` | `MODEL_OUTPUT` | - | `0cfbb1567196033217211e71e45ab2ce3bf4bbb2cde333971148e0130f4eba84` |
| LOC-037 | `input/career_run/rigorous/candidates/generated_2_raw.json` | `MODEL_GENERATED_DERIVATIVE` | `APPLICATION_CANDIDATE` | 신용보증기금 지원서 | `EXCLUDED_AS_EVIDENCE` | `MODEL_OUTPUT` | - | `101ea579ec2bcd16a1736dfef5a0f462878bc59fedd3e0b1ccbf1d54179224a5` |
| LOC-038 | `input/career_run/rigorous/candidates/generated_3.json` | `MODEL_GENERATED_DERIVATIVE` | `APPLICATION_CANDIDATE` | 신용보증기금 지원서 | `EXCLUDED_AS_EVIDENCE` | `MODEL_OUTPUT` | - | `70ee1bcb1128b5756f38c148acbbb5b4e66a60df1bcc6cb59783c541c3d5e3f0` |
| LOC-039 | `input/career_run/rigorous/candidates/generated_3_raw.json` | `MODEL_GENERATED_DERIVATIVE` | `APPLICATION_CANDIDATE` | 신용보증기금 지원서 | `EXCLUDED_AS_EVIDENCE` | `MODEL_OUTPUT` | - | `af9a7be0936bfc2a41345dab04ecff31e6e69c554c45249c3f60e88a9a53c4eb` |
| LOC-040 | `input/career_run/rigorous/candidates/generated_4.json` | `MODEL_GENERATED_DERIVATIVE` | `APPLICATION_CANDIDATE` | 신용보증기금 지원서 | `EXCLUDED_AS_EVIDENCE` | `MODEL_OUTPUT` | - | `519785e436d9d45a429020e3c35289d96eff738c400cacf4f3cdb1f057ef4589` |
| LOC-041 | `input/career_run/rigorous/candidates/generated_4_raw.json` | `MODEL_GENERATED_DERIVATIVE` | `APPLICATION_CANDIDATE` | 신용보증기금 지원서 | `EXCLUDED_AS_EVIDENCE` | `MODEL_OUTPUT` | - | `a06e407173f4d0fdfbd857f0fafa9b274097be5d90a6d17953a92e8361d1354a` |
| LOC-042 | `input/career_run/rigorous/data_package.json` | `PIPELINE_METADATA` | `RIGOROUS_SELECTION_LINEAGE` | 신용보증기금 지원서 | `PROCESS_LINEAGE_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `e52854b5a6d9614c64c8ff6028f9a0c40a1b63901bde2d0ab9227cacf1a3a27e` |
| LOC-043 | `input/career_run/rigorous/final_comparison.json` | `PIPELINE_METADATA` | `RIGOROUS_SELECTION_LINEAGE` | 신용보증기금 지원서 | `PROCESS_LINEAGE_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `1322fcaddc6e8ac76492e93658b55435278678822af3a1527b5a5a2e032cb6ab` |
| LOC-044 | `input/career_run/rigorous/judges/job_fact_auditor.json` | `MODEL_EVALUATION_DERIVATIVE` | `APPLICATION_JUDGE_OUTPUT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `MODEL_OUTPUT` | - | `df7c94eb41bd4433b9abbcb6f8636c9b498d1faa8930ca76e38d2e267f35b796` |
| LOC-045 | `input/career_run/rigorous/judges/job_fact_auditor_raw.json` | `MODEL_EVALUATION_DERIVATIVE` | `APPLICATION_JUDGE_OUTPUT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `MODEL_OUTPUT` | input/career_run/rigorous/judges/job_fact_auditor.json | `df7c94eb41bd4433b9abbcb6f8636c9b498d1faa8930ca76e38d2e267f35b796` |
| LOC-046 | `input/career_run/rigorous/judges/korean_editor.json` | `MODEL_EVALUATION_DERIVATIVE` | `APPLICATION_JUDGE_OUTPUT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `MODEL_OUTPUT` | - | `1c803aef2898adb99d6b376433ceb3e977edb643aae660e6e2fa6ac1552a7a3c` |
| LOC-047 | `input/career_run/rigorous/judges/korean_editor_raw.json` | `MODEL_EVALUATION_DERIVATIVE` | `APPLICATION_JUDGE_OUTPUT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `MODEL_OUTPUT` | input/career_run/rigorous/judges/korean_editor.json | `1c803aef2898adb99d6b376433ceb3e977edb643aae660e6e2fa6ac1552a7a3c` |
| LOC-048 | `input/career_run/rigorous/judges/recruiter.json` | `MODEL_EVALUATION_DERIVATIVE` | `APPLICATION_JUDGE_OUTPUT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `MODEL_OUTPUT` | - | `be02a1bcb10cfb387a4d7ce6cafb3f281fed430b54beded3267fcdc174846966` |
| LOC-049 | `input/career_run/rigorous/judges/recruiter_raw.json` | `MODEL_EVALUATION_DERIVATIVE` | `APPLICATION_JUDGE_OUTPUT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `MODEL_OUTPUT` | input/career_run/rigorous/judges/recruiter.json | `be02a1bcb10cfb387a4d7ce6cafb3f281fed430b54beded3267fcdc174846966` |
| LOC-050 | `input/career_run/rigorous/manifest.json` | `PIPELINE_METADATA` | `RIGOROUS_SELECTION_LINEAGE` | 신용보증기금 지원서 | `PROCESS_LINEAGE_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `cfda42d6e983d9314d1df91c58d6e9529fe71ef3bef1192c34ea0029ba092cb1` |
| LOC-051 | `input/career_run/rigorous/private_mapping.json` | `PIPELINE_METADATA` | `RIGOROUS_SELECTION_LINEAGE` | 신용보증기금 지원서 | `PROCESS_LINEAGE_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `b391075fa4d6fd7027c07e78b296661a8a92dcb324588fd3d871cf8f053b161b` |
| LOC-052 | `input/career_run/rigorous/selected.json` | `PIPELINE_METADATA` | `RIGOROUS_SELECTION_LINEAGE` | 신용보증기금 지원서 | `PROCESS_LINEAGE_ONLY` | `DERIVED_NOT_EVIDENCE` | input/career_run/draft_final.json | `de94aed7e0cdaaf22607bd4afbf649d63e91861f18d3dc94c899b655590da50b` |
| LOC-053 | `input/career_run/rigorous/synthesis.json` | `PIPELINE_METADATA` | `RIGOROUS_SELECTION_LINEAGE` | 신용보증기금 지원서 | `PROCESS_LINEAGE_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `3bd0343f0f1c1d9f66f62ef2ce4179e88e7ffd6475ec24de984eb90f37520f4d` |
| LOC-054 | `input/career_run/run.json` | `PIPELINE_METADATA` | `QUALITY_OR_RUN_AUDIT` | 신용보증기금 지원서 | `PROCESS_AUDIT_ONLY` | `DERIVED_NOT_EVIDENCE` | - | `86652102a62cdd506417a9e4b4158c314c5a3fe4ec13a8263aef7cb0a3e6e63d` |
| LOC-055 | `input/경험정리/0113_dl_51_sb (1) (1).jpg` | `PII_IMAGE` | `APPLICANT_PORTRAIT` | 지원자 | `EXCLUDED` | `PROHIBITED_FOR_COMPANY_RESEARCH` | - | `d65f8ae2d6d6360b39d0e07ec8cf41c1272e9908fe1c90b7d0e4a0be9f6cf414` |
| LOC-056 | `input/경험정리/경험정리.docx` | `APPLICANT_SOURCE` | `APPLICANT_NARRATIVE_SOURCE` | 지원자 | `APPLICANT_BRIDGE_ONLY` | `LOCAL_SOURCE_PRESENT` | - | `dbbed908faa6876fd4cab9ffa7e4728d0f9d5453bd1d18b4a5e26164f88607d1` |
| LOC-057 | `input/직무기술서/직무기술서_상담직.pdf` | `OUT_OF_SCOPE_OFFICIAL_DOCUMENT` | `OTHER_EMPLOYER_JOB_DESCRIPTION` | 한국도로공사서비스(주) | `EXCLUDED_ENTITY_MISMATCH` | `OUT_OF_SCOPE` | - | `c085653246cb209d0db93ae981babe6c92e88dbee01b4212db6a328fbc52e509` |
| LOC-058 | `input/직무기술서/직무기술서_영업직(보훈).pdf` | `OUT_OF_SCOPE_OFFICIAL_DOCUMENT` | `OTHER_EMPLOYER_JOB_DESCRIPTION` | 한국도로공사서비스(주) | `EXCLUDED_ENTITY_MISMATCH` | `OUT_OF_SCOPE` | - | `646cab9a010221089b8e0237c8407cc391754ef1926b78870826d02c80a71881` |
| LOC-059 | `input/직무기술서/직무기술서_영업직(사무영업).pdf` | `OUT_OF_SCOPE_OFFICIAL_DOCUMENT` | `OTHER_EMPLOYER_JOB_DESCRIPTION` | 한국도로공사서비스(주) | `EXCLUDED_ENTITY_MISMATCH` | `OUT_OF_SCOPE` | - | `fb6f312f73fa836818743f1d3a0770508bb54f6a6989ae56ef67289e5ae3724f` |
| LOC-060 | `input/직무기술서/직무기술서_영업직(사회형평).pdf` | `OUT_OF_SCOPE_OFFICIAL_DOCUMENT` | `OTHER_EMPLOYER_JOB_DESCRIPTION` | 한국도로공사서비스(주) | `EXCLUDED_ENTITY_MISMATCH` | `OUT_OF_SCOPE` | - | `41bd180560657128783299056e52465d00a0f77d1594e125cc94543bfcd06c6e` |
| LOC-061 | `input/직무기술서/직무기술서_영업직(안전).pdf` | `OUT_OF_SCOPE_OFFICIAL_DOCUMENT` | `OTHER_EMPLOYER_JOB_DESCRIPTION` | 한국도로공사서비스(주) | `EXCLUDED_ENTITY_MISMATCH` | `OUT_OF_SCOPE` | - | `4b63a0416ce924da02f8002117bd9beb58500db361bf0468c10467db53bc3bbd` |
| LOC-062 | `input/직무기술서/직무기술서_영업직(정보통신).pdf` | `OUT_OF_SCOPE_OFFICIAL_DOCUMENT` | `OTHER_EMPLOYER_JOB_DESCRIPTION` | 한국도로공사서비스(주) | `EXCLUDED_ENTITY_MISMATCH` | `OUT_OF_SCOPE` | - | `1b4318e4d1d29f1ca125a47d9ed71e040e9715190b556112498383fc88ac509e` |

## 7. STEP 1 게이트

- 회사 법적 지위·브랜드 동일성·공식 사업 범위: `NEEDS_VERIFICATION`
- 공고 원문의 기관명·채용분야·담당업무·문항: 로컬 스냅샷 범위에서 확인
- 지원 마감일·근무기간·근무지·자격·배치 조직: `UNVERIFIED`
- 재무 비교기간·뉴스 검색 시작일·비교대상 집합: `UNVERIFIED`
- STEP 11 HARD FAIL: `NOT_EVALUATED_AT_STEP_1`
