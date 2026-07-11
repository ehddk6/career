{
  "mode": "score",
  "format": "json",
  "overall": 33.3,
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
      "rawScore": 4.2,
      "weighted": 0.8
    },
    {
      "name": "style",
      "weight": 0.18,
      "detected": null,
      "rawScore": 5.6,
      "weighted": 1
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
    "overall": 33.3,
    "passed": false,
    "exitCode": 3
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | 없음 | 0.0 | 0.0 |\n| language | 0.18 | Low: 반복적·공식적 직무어가 일부 있으나 패턴 기준에는 약함 | 4.2 | 0.8 |\n| style | 0.18 | Low: “그 결과”, “이후” 중심의 반복 연결 | 5.6 | 1.0 |\n| communication | 0.13 | 없음 | 0.0 | 0.0 |\n| filler | 0.08 | Low: “~다는 점”, “~할 수 있었습니다”식 완충 표현 일부 | 8.3 | 0.7 |\n| structure | 0.15 | Medium: 각 문항이 경험→정리→결과→공사 적용 구조로 반복됨 | 13.3 | 2.0 |\n| viral-hook | 0.1 | 없음 | 0.0 | 0.0 |\n| **Overall** | | | | **4.5 (±10)** |\n\n```yaml\ntone: null\ntone_source: profile_only\n```",
  "scores": {
    "llm": {
      "overall": 4.5,
      "interpretation": "human"
    },
    "deterministic": {
      "overall": 33.3,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 9,
      "hotParagraphs": 3,
      "signalScore": 21.1,
      "bands": {
        "burstiness": {
          "low": 3,
          "mid": 0,
          "high": 1,
          "null": 5
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
      "llmOverall": 4.5,
      "deterministicOverall": 33.3,
      "overall": 33.3
    }
  }
}