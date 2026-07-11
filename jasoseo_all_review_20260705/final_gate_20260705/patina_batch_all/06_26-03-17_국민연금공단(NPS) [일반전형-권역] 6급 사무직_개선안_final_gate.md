{
  "mode": "score",
  "format": "json",
  "overall": 36.4,
  "categories": [
    {
      "name": "content",
      "weight": 0.18,
      "detected": null,
      "rawScore": 0,
      "weighted": 0
    },
    {
      "name": "language",
      "weight": 0.18,
      "detected": null,
      "rawScore": 12.5,
      "weighted": 2.3
    },
    {
      "name": "style",
      "weight": 0.18,
      "detected": null,
      "rawScore": 11.1,
      "weighted": 2
    },
    {
      "name": "communication",
      "weight": 0.13,
      "detected": null,
      "rawScore": 0,
      "weighted": 0
    },
    {
      "name": "filler",
      "weight": 0.08,
      "detected": null,
      "rawScore": 8.3,
      "weighted": 0.7
    },
    {
      "name": "structure",
      "weight": 0.15,
      "detected": null,
      "rawScore": 20,
      "weighted": 3
    },
    {
      "name": "viral-hook",
      "weight": 0.1,
      "detected": null,
      "rawScore": 0,
      "weighted": 0
    }
  ],
  "tone": {
    "tone": null,
    "tone_source": "profile_only",
    "tone_evidence": [],
    "tone_confidence": null
  },
  "mps": null,
  "gateResult": {
    "threshold": 30,
    "overall": 36.4,
    "passed": false,
    "exitCode": 3
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | 없음 | 0.0 | 0.0 |\n| language | 0.18 | 유의어 순환 Low, 3의 법칙 Medium | 12.5 | 2.3 |\n| style | 0.18 | `~고 있다` 진행형 Low, 공식어 Low | 11.1 | 2.0 |\n| communication | 0.13 | 없음 | 0.0 | 0.0 |\n| filler | 0.08 | 채움 표현 Low | 8.3 | 0.7 |\n| structure | 0.15 | 구조적 반복 High | 20.0 | 3.0 |\n| viral-hook | 0.1 | 없음 | 0.0 | 0.0 |\n| **Overall** | | | | **8.0 (±10)** |\n\n```yaml\nphase_6:\n  score: 8.0\n  interpretation: 사람다움\n  tone: null\n  tone_source: profile_only\n  notes:\n    - 문항마다 같은 마무리 문장과 처리 순서가 반복되어 구조적 반복 신호가 가장 큽니다.\n    - 과장, 챗봇 표현, 바이럴 훅은 거의 보이지 않습니다.\n```",
  "scores": {
    "llm": {
      "overall": 8,
      "interpretation": "human"
    },
    "deterministic": {
      "overall": 36.4,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 11,
      "hotParagraphs": 4,
      "signalScore": 20.4,
      "bands": {
        "burstiness": {
          "low": 4,
          "mid": 0,
          "high": 0,
          "null": 7
        },
        "mattr": {
          "low": 0,
          "mid": 0,
          "high": 10,
          "null": 1
        },
        "lexicon": {
          "hot": 0,
          "threshold": 3
        },
        "koDiagnostics": {
          "hot": 0,
          "thresholds": {
            "minSentences": 4,
            "minEojeols": 20,
            "spacing": {
              "maxEojeolLengthCV": 0.38
            },
            "comma": {
              "maxPerSentence": 1
            },
            "posProxy": {
              "minMatchedCount": 10,
              "maxClassDiversity": 0.26
            }
          }
        },
        "markupLeakage": {
          "leaked": false,
          "hits": 0,
          "floor": 90
        },
        "discourseTells": {
          "hot": false,
          "fakeCandor": {
            "count": 0,
            "hits": [],
            "hot": false,
            "threshold": 2
          },
          "thematicBreaks": {
            "count": 0,
            "adjacentToHeading": 0,
            "hot": false,
            "threshold": 3
          }
        },
        "structuralClassifier": {
          "available": false,
          "hot": null,
          "score": null,
          "floor": 0
        }
      }
    },
    "preference": {
      "reason": "deterministic-divergence",
      "selected": "deterministic",
      "threshold": 20,
      "llmOverall": 8,
      "deterministicOverall": 36.4,
      "overall": 36.4
    }
  }
}