# Career Pipeline 사용법

Career Pipeline은 취업 폴더의 기존 자료를 읽고 사실 충돌을 검사한 뒤, Codex가 최신 공식 자료조사·자기소개서·면접팩을 생성하도록 돕는 저장소 로컬 스킬입니다.

## 초기 준비

PowerShell에서 최초 한 번 실행합니다.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Codex에서 이 폴더를 열면 `.agents/skills/career-pipeline/` 스킬을 사용할 수 있습니다.

## 자연어 호출

```text
HUG 공고와 현재 자소서를 기준으로 자료조사부터 면접팩까지 실행해줘.
```

또는 스킬을 명시합니다.

```text
$career-pipeline
대상: HUG 체험형 인턴 금융·기금(강원)
공고: <URL 또는 PDF>
초안: 26-06-21_주택도시보증공사(HUG) 일반전형_금융·기금(강원).docx
```

## 내부 명령

Codex 스킬은 먼저 다음 명령을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline prepare `
  --root . `
  --target "HUG 금융·기금(강원)" `
  --draft "26-06-21_주택도시보증공사(HUG) 일반전형_금융·기금(강원).docx"
```

명령은 `career_runs/` 아래에 새 run 디렉터리를 만듭니다.

## 충돌 해결과 재개

`run.json`의 `status`가 `blocked`면 자기소개서를 작성하지 않습니다. `03_충돌검사.md`에 나온 실제 값과 근거를 확인해 Codex에 답합니다. Codex는 확정 값을 같은 run 디렉터리의 `fact_overrides.yaml`에 기록합니다.

재개 예시:

```powershell
.\.venv\Scripts\python.exe -m career_pipeline prepare `
  --root . `
  --target "HUG 금융·기금(강원)" `
  --draft "26-06-21_주택도시보증공사(HUG) 일반전형_금융·기금(강원).docx" `
  --resume "career_runs/<run-dir>"
```

기존 자기소개서·경험 파일은 수정하지 않습니다.

## 최종 검증

Codex가 조사·전략·자기소개서·면접팩을 작성하면 다음을 실행합니다.

```powershell
.\.venv\Scripts\python.exe -m career_pipeline finalize --run "career_runs/<run-dir>"
```

`complete`가 아니면 `run.json` 의 `validation_issues`를 확인해 해당 답변만 수정합니다.

## 결과물

- `01_자료목록.md`: 사용·제외·중복·추출 실패 파일
- `02_사실원장.json`: 검출된 수치와 근거 문단
- `03_충돌검사.md`: 서로 다른 수치·기간·역할
- `04_기업직무조사.md`: 최신 공식 웹 출처
- `05_문항전략.md`: 문항별 경험 배치와 핵심 메시지
- `06_자기소개서.md`: 최종 답변
- `06_자기소개서.docx`: 제출·복사용 Word 문서
- `07_자기소개서_검토보고서.md`: 글자 수·근거·블라인드 검사
- `08_면접대비팩.md`: 1분 자기소개·꼬리질문·압박질문·방어 근거
- `run.json`: 실행 상태와 검증 오류

## 기본 제외 자료

`Chrome 비밀번호.csv`, `학교성적/`, `자격증/`, `경력증명서/`, `.git/`, `.venv/`, 기존 `career_runs/`는 기본 제외됩니다. 제외된 민감 파일은 해시 계산을 위해 열지도 않습니다.
