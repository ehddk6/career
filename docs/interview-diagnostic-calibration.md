# Calibrated Adaptive Interview — Diagnostic Yield

## 목적

기존 Structured-Adaptive Interview Intelligence의 `selection_utility`는 명시적인 휴리스틱 prior다. 새 calibration 계층은 실제 모의면접 세션에서 어떤 probe family가 어떤 평가 차원에서 유의미한 진단 신호를 만들어냈는지 aggregate 수준으로 학습해 이 prior를 보정한다.

이 값은 **합격확률이 아니며 psychometric information function도 아니다.** 현재 구현의 명칭은 `diagnostic_yield_proxy`다.

## 저장하지 않는 것

`.career_profile/interview_diagnostic_calibration.json`에는 다음을 저장하지 않는다.

- 과거 답변 원문
- answer excerpt
- 지원자 사실
- 회사 사실
- 합격/불합격 확률

저장되는 것은 `probe family × dimension`의 observation count, yield EMA, last yield뿐이다.

## 학습 신호

- deterministic gate가 해당 dimension을 weak dimension으로 검출하면 강한 진단 신호로 본다.
- semantic judge를 사용한 경우 0~4 bounded score가 중립점에서 얼마나 벗어났는지를 진단 신호로 사용한다.
- semantic judge가 없고 deterministic weakness도 없으면 낮은 pass-signal prior만 기록한다.

따라서 모델 점수가 factual authority가 되지 않는다. 이 calibration은 **다음에 무엇을 물어볼지**만 조정한다.

## Shrinkage와 영향 제한

관측이 적은 family/dimension은 prior yield 0.5, prior strength 4로 수축한다. calibration이 기존 `base_diagnostic_value`에 줄 수 있는 영향은 최대 ±0.6으로 제한한다. 표준화 코어 질문은 calibration 대상이 아니며 항상 adaptive probe보다 먼저 수행된다.

## 실행 흐름

```text
standardized core
  ↓
adaptive probe
  ↓
deterministic + optional semantic evaluation
  ↓
weakness aggregate update
+ diagnostic-yield aggregate update
  ↓
shrinkage-calibrated probe utility
  ↓
next adaptive probe
```

`python -m career_pipeline.interview_intelligence evaluate ... --update-profile`은 기존 weakness profile과 diagnostic calibration profile을 함께 갱신한다. 이후 `next_question.selection_reason`은 adaptive 질문인 경우 `calibrated_expected_diagnostic_utility`가 된다.

Golden Path에서 면접 설계도를 다시 컴파일할 때 calibration profile의 SHA도 interview-stage fingerprint에 포함되므로 학습 상태가 바뀌면 오래된 `08_면접지능설계.json`을 그대로 재사용하지 않는다.
