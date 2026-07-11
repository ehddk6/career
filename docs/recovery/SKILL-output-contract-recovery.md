# SKILL.md / output-contract.md 사용자 수정 복구 절차

## 배경

2026-06-23~25 세션에서 v2 통합(devswha/career-pipeline-v2) 중 다음 두 파일의 사용자 원래 수정분이 v2 버전으로 덮어씌워졌습니다:

- .agents/skills/career-pipeline/SKILL.md
- .agents/skills/career-pipeline/references/output-contract.md

조사 결과 CLI 범위에서 복구 가능한 후보는 발견되지 않았습니다 (git fsck, reflog, stash, 다른 branch/worktree, .codex 메모리, 임시 파일, OneDrive 충돌 사본 모두 확인). 사용자가 다음 원천에서 수동으로 확인해야 합니다.

## 현재 상태 vs 이전 상태

| 파일 | committed (73ab934) | v2 (덮어쓰기 후) |
|---|---|---|
| SKILL.md | 67줄, SHA 1832863d0d0e3351 | 102줄, SHA cf82f05b55c7b55b |
| output-contract.md | 31줄, SHA 6d659dd8ad32379d | 35줄, SHA 616e41909a331af8 |

## 복구 원천 1: OneDrive 웹 버전 기록

### 확인 절차
1. https://onedrive.live.com 접속
2. 자격 증명으로 로그인
3. 문서 -> 취업 폴더로 이동
4. .agents\skills\career-pipeline\SKILL.md 우클릭 -> 버전 기록
5. **2026-06-22~23 사이의 버전** 확인
6. 해당 버전이 v2 덮어쓰기(2026-06-23~25) **이전**이면 사용자의 원래 수정본

### 확인 대상 파일
- \.agents\skills\career-pipeline\SKILL.md
- \.agents\skills\career-pipeline\references\output-contract.md

### 확인 시점 범위
- 시작: 2026-06-22 (이전 세션 종료 시점)
- 종료: 2026-06-23 (v2 덮어쓰기 시작)

## 복구 원천 2: 편집기 로컬 히스토리

### Visual Studio Code
1. VS Code에서 해당 파일 열기
2. Timeline 탭 (왼쪽 탐색기 옆에 있을 수 있음, 없으면 View > Open View > Timeline)
3. **2026-06-22~23 시점의 항목** 확인
4. 사용자 수정 시점의 항목 선택 -> 내용 비교

### 확인 대상
- .agents/skills/career-pipeline/SKILL.md
- .agents/skills/career-pipeline/references/output-contract.md

## 복구 원천 3: Windows 파일 히스토리

### 확인 절차
1. 제어판 -> 파일 히스토리 (Windows 10/11)
2. OneDrive 폴더가 포함되어 있는지 확인
3. 2026-06-22~23 시점의 백업 찾아보기
4. \.agents\skills\career-pipeline\SKILL.md 및 eferences\output-contract.md 찾기

## 복구 후보를 찾은 후 결정 절차

### Step 1: 사용자 원래 수정본 식별
찾은 후보가 다음 조건을 만족하면 사용자 원래 수정본:
- SHA-256이 committed(73ab934)와 다름
- SHA-256이 v2 덮어쓰기 후(cf82f05b55c7b55b 등)와 다름
- v2 통합이 덮어쓰기한 **이전 시점**의 버전

### Step 2: diff 확인
v2 현재 버전과 사용자 원래 수정본을 비교:
- 사용자 원래 수정본이 v2 내용 + 추가 변경 -> 그대로 적용
- 사용자 원래 수정본이 v2와 충돌 -> 수동 병합 필요

### Step 3: 적용 (수동, 사용자 승인 후)
다음 중 하나를 선택 (각각 trade-off 있음):

**옵션 A: 사용자 원래 버전 복원**
- 장점: 사용자 의도 100% 보존
- 단점: v2 기능 문서화 손실

**옵션 B: v2 위에 사용자 변경 병합**
- 장점: v2 + 사용자 의도 모두 보존
- 단점: 수동 병합 작업 필요

**옵션 C: 사용자 변경 사항만 v2에 패치**
- 장점: v2 유지, 사용자 의도 부분 보존
- 단점: 어떤 변경이 v2에 이미 있는지 확인 필요

## 복구를 찾지 못한 경우

위 3개 원천 모두에서 후보를 찾지 못하면:
- 현재 v2 버전을 그대로 유지
- 차이점을 별도 문서로 기록 (docs/recovery/known-differences.md)
- 다음 v2 업데이트 시 사용자 변경 사항을 다시 검토

## 연락처

이 절차에 대한 질문이 있으면:
- 세션에서 직접 질문
- docs/recovery/ 디렉토리에 새 메모 추가

## 변경 이력

- 2026-06-26: 초안 작성 (v5.4.0 롤백 후)
