# 벤치마크 설계

- 입력: 동일 공고, 경험 원장, 공식 근거, 기준일, DATA PACKAGE
- 조건: 동일 모델 능력군과 호출 예산, 원본 파일 불변
- 블라인드: 시스템명·전략명·파일 순서 제거
- 1차: 승인 밖 사실, 수치, 기여 과장, 금지 claim, 참조 불일치 HARD FAIL
- 2차: 회사조사 8개, 자기소개서 11개, 면접 7개 차원별 X/Y/TIE
- 필수 기록: `choice`, `reason`, `decisive_difference`, `evidence_refs`
- 판정: 모든 26개 차원 우세만 `ALL_DIMENSIONS_AHEAD`
- 제한: 외부 방식과 개선본 조정은 최대 두 차례

템플릿은 `python -m career_pipeline benchmark init`, 검증은 `benchmark validate`로 수행한다.
