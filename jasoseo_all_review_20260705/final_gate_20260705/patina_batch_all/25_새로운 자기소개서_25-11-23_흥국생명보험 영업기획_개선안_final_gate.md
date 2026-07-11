{
  "mode": "score",
  "format": "json",
  "overall": 33.3,
  "categories": [
    {
      "name": "content",
      "weight": 0.18,
      "detected": null,
      "rawScore": 5.6,
      "weighted": 1
    },
    {
      "name": "language",
      "weight": 0.18,
      "detected": null,
      "rawScore": 8.3,
      "weighted": 1.5
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
      "rawScore": 16.7,
      "weighted": 1.3
    },
    {
      "name": "structure",
      "weight": 0.15,
      "detected": null,
      "rawScore": 26.7,
      "weighted": 4
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
    "overall": 33.3,
    "passed": false,
    "exitCode": 3
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | 피상적 결과 서술 Low | 5.6 | 1.0 |\n| language | 0.18 | AI 특유 어휘 Low, 유사 표현 반복 Low | 8.3 | 1.5 |\n| style | 0.18 | 연결 표현 반복 Low, 공식어 사용 Low | 11.1 | 2.0 |\n| communication | 0.13 | 없음 | 0.0 | 0.0 |\n| filler | 0.08 | 채움 표현 Low, 약한 헤징 Low | 16.7 | 1.3 |\n| structure | 0.15 | 문항별 구조 반복 Medium, 번역체/어색한 명사 연결 Medium | 26.7 | 4.0 |\n| viral-hook | 0.1 | 없음 | 0.0 | 0.0 |\n| **Overall** | | | | **9.8 (±10)** |\n\n```yaml\ntone: null\ntone_source: profile_only\n```",
  "scores": {
    "llm": {
      "overall": 9.8,
      "interpretation": "human"
    },
    "deterministic": {
      "overall": 33.3,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 9,
      "hotParagraphs": 3,
      "signalScore": 17,
      "bands": {
        "burstiness": {
          "low": 3,
          "mid": 0,
          "high": 0,
          "null": 6
        },
        "mattr": {
          "low": 0,
          "mid": 0,
          "high": 8,
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
      "llmOverall": 9.8,
      "deterministicOverall": 33.3,
      "overall": 33.3
    }
  }
}