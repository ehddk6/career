# Career Pipeline 1차 개선 묶음 (2026-06-23)

## 배경

증거 기반 평가에서 총점 62/100 확인. 6개 발견사항을 1차 개선으로 해결.

## 범위

| ID | 우선순위 | 항목 | 파일 |
|---|---|---|---|
| F-06 | P2 | pyproject.toml 패키지 발견 설정 | pyproject.toml |
| F-07 | P2 | EXCLUDED_DIRS에 임시 디렉토리 추가 | career_pipeline/inventory.py |
| F-05 | P2 | METRIC regex에 조원 단위 추가 | career_pipeline/facts.py |
| F-01 | P1 | KNOWN_ORGANIZATIONS 목록 확장 | career_pipeline/validation.py |
| F-02 | P1 | 04_채용근거.json 검증 추가 | career_pipeline/orchestrator.py |
| F-03 | P1 | [확인 필요] 마커 검사 추가 | career_pipeline/validation.py |

## 제외 항목

- F-04 (경력증명서/ 제외 설계): 별도 승인 필요
- F-08 (클레임 수 제한): 우선순위 낮음
- F-09 (프롬프트 주입): 구조적 한계
- F-10 (링크 교차 검사): F-02 구현 후 일부 해결

## 완료 조건

- pytest 전체 통과
- pip install -e . 성공
- 합성 데이터로 prepare → finalize 검증
- 개선 후 예상 점수: 75/100
