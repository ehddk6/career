{
  "mode": "score",
  "format": "json",
  "overall": 36.4,
  "categories": [
    {
      "name": "content",
      "weight": 0.18,
      "detected": null,
      "rawScore": 11.1,
      "weighted": 2
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
      "rawScore": 13.3,
      "weighted": 2
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
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | Pattern 3 Low, Pattern 5 Low | 11.1 | 2.0 |\n| language | 0.18 | Pattern 7 Low, Pattern 11 Medium | 12.5 | 2.3 |\n| style | 0.18 | Pattern 13 Low, Pattern 18 Low | 11.1 | 2.0 |\n| communication | 0.13 | None | 0.0 | 0.0 |\n| filler | 0.08 | Pattern 22 Low | 8.3 | 0.7 |\n| structure | 0.15 | Pattern 25 Medium | 13.3 | 2.0 |\n| viral-hook | 0.1 | None | 0.0 | 0.0 |\n| **Overall** | | | | **8.9 (±10)** |\n\n판정: **사람다움** 범위입니다.  \n주요 신호는 문항마다 비슷한 구조가 반복되는 점, “사회보장정보원/정보시스템/데이터 정확성/사용자 안내” 같은 핵심어가 다소 기계적으로 반복되는 점입니다. 다만 과장, 챗봇 말투, 근거 없는 최신 정보 단정, 바이럴 훅은 거의 없습니다.\n\n```yaml\nphase_6:\n  tone: null\n  tone_source: profile_only\n  ai_likeness_score: 8.9\n  score_band: human\n  variance: \"±10\"\n```",
  "scores": {
    "llm": {
      "overall": 8.9,
      "interpretation": "human"
    },
    "deterministic": {
      "overall": 36.4,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 11,
      "hotParagraphs": 4,
      "signalScore": 20.7,
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
      "llmOverall": 8.9,
      "deterministicOverall": 36.4,
      "overall": 36.4
    }
  }
}