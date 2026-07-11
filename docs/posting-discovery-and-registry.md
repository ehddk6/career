# 공식 공고 탐색과 Registry

Phase 3 초기 구현은 공식 allowlist 출처에서 공고 URL을 발견하고, 공고 원문을 `PostingRecord`로 고정한 뒤 registry와 사용자 검토 queue에 저장한다. 브라우저 자동화·로그인·원서 입력·제출은 포함하지 않는다.

## 허용 출처

지원하는 출처 유형은 다음과 같다.

- `manual_url`: 사용자가 직접 지정한 공고 URL 한 건
- `official_list_page`: 공식 목록 페이지의 상세 링크
- `official_rss`: RSS/Atom 링크
- `official_sitemap`: 허용된 사이트맵 링크
- `official_json_api`: 사용자가 명시한 공식 공개 JSON API

모든 URL은 HTTPS·allowlist·공개 IP·redirect 재검증·응답 크기·콘텐츠 유형 제한을 통과해야 한다. 로그인·개인정보·지원서 작성 페이지와 비허용 도메인은 후보에서 제외한다. 페이지 재귀 탐색은 하지 않으며 페이지네이션은 명시적으로 설정한 경우에만 최대 3페이지까지 허용한다.

## 저장 위치

```text
.career_profile/
  discovery_sources.json
  posting_registry/
    registry.json
    events.jsonl
    snapshots/
    discovery_runs/
```

registry 인덱스에는 원문 전체를 저장하지 않는다. 원문은 SHA-256 이름의 snapshot으로 분리하고, 이벤트에는 상태와 최소 메타데이터만 기록한다. registry JSON과 source 설정은 원자적으로 저장하며 registry lock을 사용한다.

## 상태 의미

공고 발견 상태는 다음과 같다.

- `new`: 대응되는 기존 공고가 없음
- `exact_duplicate`: 같은 URL·공식 ID와 같은 raw/normalized hash
- `content_duplicate`: 다른 URL이지만 normalized hash가 같음
- `changed`: 같은 공고 식별자 또는 URL에서 의미 있는 내용이 변경됨
- `unchanged`: 정규화된 내용이 동일함
- `expired`: 평가 시각 기준 마감됨
- `closed`: 모집 종료가 명시됨
- `manual_review`: 마감일·timezone·관계 또는 파싱 결과를 확정할 수 없음

날짜만 있는 마감일은 공고 timezone의 23:59:59로 해석한다. timezone이 없으면 임의로 한국 시간으로 바꾸지 않고 `manual_review`로 보낸다. 평가 시각은 `--evaluation-time`으로 명시한다.

## 자격 판정과 queue

`new` 또는 `changed` 공고만 기본 자격 판정 대상이다. `expired`, `closed`, `content_duplicate`, 필수 조건 파싱 실패, timezone 불명 공고는 자동 자격 판정을 하지 않고 queue에 수동 검토 사유를 남긴다.

자격 상태는 기존 Phase 2의 네 상태를 그대로 사용한다. `ineligible`은 기본 queue에 등록하지 않으며, `eligible`, `eligible_with_gaps`, `manual_review`는 `pending` queue로 등록한다. 공고가 변경되면 기존 승인 queue는 `superseded`가 되고 변경 snapshot에 대한 새 queue 항목이 생성된다. queue 승인은 실제 원서 제출 승인이 아니다.

## 명령 예시

```powershell
python -m career_pipeline discovery source-add `
  --root . `
  --organization "공식기관" `
  --type official_list_page `
  --url "https://official.example/jobs" `
  --allow-domain "official.example"

python -m career_pipeline discovery run `
  --root . `
  --source-id "source-..." `
  --evaluation-time "2026-07-11T18:00:00+09:00" `
  --applicant-profile ".career_profile/applicant_profile.json"

python -m career_pipeline registry list --root .
python -m career_pipeline queue list --root . --status pending
python -m career_pipeline queue decide --root . --queue-id "queue-..." --decision approved
```

외부 사이트를 대상으로 한 테스트는 실행하지 않는다. 테스트는 fake resolver, fake downloader, local HTML/XML/JSON fixture, fake evaluation time으로 수행한다.
