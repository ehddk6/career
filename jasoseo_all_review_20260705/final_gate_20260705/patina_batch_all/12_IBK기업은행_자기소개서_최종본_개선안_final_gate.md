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
      "rawScore": 8.3,
      "weighted": 1.5
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
    "overall": 33.3,
    "passed": false,
    "exitCode": 3
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | 0/6 | 0.0 | 0.0 |\n| language | 0.18 | 1/8 | 8.3 | 1.5 |\n| style | 0.18 | 1/6 | 5.6 | 1.0 |\n| communication | 0.13 | 0/4 | 0.0 | 0.0 |\n| filler | 0.08 | 1/4 | 8.3 | 0.7 |\n| structure | 0.15 | 1/5 | 20.0 | 3.0 |\n| viral-hook | 0.1 | 0/9 | 0.0 | 0.0 |\n| **Overall** | | | | **6.2 (±10)** |\n\n해석: **사람다움** 범위입니다. 다만 문항 2와 문항 3의 문장 흐름과 일부 문장이 거의 반복되어 구조 패턴 점수가 가장 크게 반영됐습니다.\n\n---\ntone: null\ntone_source: profile_only\ntone_evidence: []\ntone_confidence: null\n---",
  "scores": {
    "llm": {
      "overall": 6.2,
      "interpretation": "human"
    },
    "deterministic": {
      "overall": 33.3,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 9,
      "hotParagraphs": 3,
      "signalScore": 21.5,
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
      "llmOverall": 6.2,
      "deterministicOverall": 33.3,
      "overall": 33.3
    }
  }
}