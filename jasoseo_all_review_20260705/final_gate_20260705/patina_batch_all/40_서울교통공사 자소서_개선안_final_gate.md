{
  "mode": "score",
  "format": "json",
  "overall": 41.2,
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
      "rawScore": 16.7,
      "weighted": 3
    },
    {
      "name": "style",
      "weight": 0.18,
      "detected": null,
      "rawScore": 22.2,
      "weighted": 4
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
      "rawScore": 33.3,
      "weighted": 2.7
    },
    {
      "name": "structure",
      "weight": 0.15,
      "detected": null,
      "rawScore": 33.3,
      "weighted": 5
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
    "overall": 41.2,
    "passed": false,
    "exitCode": 3
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | #3 피상적 분석 M | 11.1 | 2.0 |\n| language | 0.18 | #9 부정 병렬 M; #10 3의 법칙 L; #12 장황 조사 L | 16.7 | 3.0 |\n| style | 0.18 | #13 연결 표현 M; #18 공식어 M | 22.2 | 4.0 |\n| communication | 0.13 | 없음 | 0.0 | 0.0 |\n| filler | 0.08 | #22 채움 M; #23 헤징 M | 33.3 | 2.7 |\n| structure | 0.15 | #25 구조적 반복 H; #26 번역체 M | 33.3 | 5.0 |\n| viral-hook | 0.1 | 없음 | 0.0 | 0.0 |\n| **Overall** | | | | **16.7 (±10)** |\n\n```yaml\ntone: null\ntone_source: profile_only\ntone_evidence: []\ntone_confidence: null\n```",
  "scores": {
    "llm": {
      "overall": 16.7,
      "interpretation": "mostly human"
    },
    "deterministic": {
      "overall": 41.2,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 17,
      "hotParagraphs": 7,
      "signalScore": 25.7,
      "bands": {
        "burstiness": {
          "low": 7,
          "mid": 0,
          "high": 5,
          "null": 5
        },
        "mattr": {
          "low": 0,
          "mid": 0,
          "high": 16,
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
      "llmOverall": 16.7,
      "deterministicOverall": 41.2,
      "overall": 41.2
    }
  }
}