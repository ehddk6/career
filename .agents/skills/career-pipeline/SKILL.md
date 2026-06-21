---
name: career-pipeline
description: 취업 폴더의 DOCX, PDF, XLSX, TXT 자료와 작성 중인 자기소개서를 분석하고, 사실·수치 충돌을 검증한 뒤 최신 공식 자료조사, 문항 전략, 자기소개서 Markdown·DOCX, 검토 보고서, 면접 대비팩을 통합 생성한다. 자소서 초안 검토, 채용공고 기반 기업·직무 조사, 면접 질문 준비, 또는 이 전 과정을 한 번에 실행해 달라는 요청에 사용한다.
---

# Career Pipeline

검증 가능한 사실만 사용해 자료 분석부터 면접 방어팩까지 생성한다. Python 엔진이 파일·수치·제약을 판정하고 Codex가 최신 공식 출처 조사와 문장 합성을 담당한다.

## 필수 입력

다음을 파악한다.

- 지원 기관·기업과 직무
- 채용공고 URL 또는 로컬 파일
- 작성 중인 자기소개서 파일
- 원본 취업 자료 폴더

없는 입력이 결과를 바꾸면 한 번에 하나만 질문한다. 공고 URL이 없지만 공고 파일이 있으면 질문하지 않는다.

## 실행 순서

1. 작업공간 루트에서 다음을 실행한다.

```powershell
python -m career_pipeline prepare --root "<workspace>" --target "<target>" --draft "<draft>" --posting "<posting>"
```

`--posting`은 없으면 생략한다. 명령이 출력한 run 디렉터리의 `run.json`을 읽는다.

2. `status` 가 `blocked`면 `03_충돌검사.md`만 읽고 그 문서의 확인 질문을 사용자에게 묻는다. 초안을 작성하지 않는다. 확정 값을 run 디렉터리의 `fact_overrides.yaml`에 `override key: 확정값`으로 기록한 뒤 다음으로 재개한다.

```powershell
python -m career_pipeline prepare --root "<workspace>" --target "<target>" --draft "<draft>" --posting "<posting>" --resume "<run-dir>"
```

3. `status` 가 `ready_for_research`면 매 실행마다 최신 웹 조사를 수행한다. 채용공고 원문, 기관·기업 공식 사이트, ALIO·정부·공시, 업무 규정, 공식 보고서 순으로 사용한다. 핵심 주장 마다 직접 링크를 남겨 `04_기업직무조사.md`를 작성한다. 공식 출처로 확인하지 못한 정보는 `[확인 필요]`로 분리하고 제출 본문에서 제외한다.

4. `02_사실원장.json`, `fact_overrides.yaml`, 문항, 공식 조사를 연결해 `05_문항전략.md`를 작성한다. 각 문항에 분류, 선택 경험, 정확한 근거 파일, 핵심 메시지, 기관 연결, 부족 근거를 넣는다.

5. [output contract](references/output-contract.md)를 읽고 `draft.json`과 `08_면접대비팩.md`를 작성한다. 참고 자소서의 문구를 복사하지 않고, `confirmed`로 확인된 사실 밖의 수치·기간·역할·자격을 만들지 않는다.

6. 다음을 실행한다.

```powershell
python -m career_pipeline finalize --run "<run-dir>"
```

`blocked_validation`이면 `run.json` 의 `validation_issues`만 수정하고 finalize를 다시 실행한다. `complete`일 때만 완료로 보고한다.

## 개인정보

- `Chrome 비밀번호.csv`, `학교성적/`, `자격증/`, `경력증명서/`는 기본 제외한다.
- 사용자가 특정 증빙 파일을 명시적으로 지정하지 않으면 읽지 않는다.
- 성명, 연락처, 주소, 식별번호, 취업 파일 본문을 웹 검색어·URL·외부 폼으로 전송하지 않는다.

## 완료 보고

다음 파일을 모두 확인하고 경로를 보고한다.

- `04_기업직무조사.md`
- `05_문항전략.md`
- `06_자기소개서.md`
- `06_자기소개서.docx`
- `07_자기소개서_검토보고서.md`
- `08_면접대비팩.md`
- `run.json`
