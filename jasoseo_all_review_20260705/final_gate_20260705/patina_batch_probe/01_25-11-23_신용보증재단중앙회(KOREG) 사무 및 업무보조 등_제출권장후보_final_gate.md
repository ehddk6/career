{
  "mode": "score",
  "format": "json",
  "overall": 1.8,
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
      "rawScore": 0,
      "weighted": 0
    },
    {
      "name": "structure",
      "weight": 0.15,
      "detected": null,
      "rawScore": 0,
      "weighted": 0
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
    "overall": 1.8,
    "passed": true,
    "exitCode": 0
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | 0/6 | 0.0 | 0.0 |\n| language | 0.18 | 1/8: 부정 병렬구조 Low | 4.2 | 0.8 |\n| style | 0.18 | 1/6: 연결 표현 Low | 5.6 | 1.0 |\n| communication | 0.13 | 0/4 | 0.0 | 0.0 |\n| filler | 0.08 | 0/4 | 0.0 | 0.0 |\n| structure | 0.15 | 0/5 | 0.0 | 0.0 |\n| viral-hook | 0.1 | 0/9 | 0.0 | 0.0 |\n| **Overall** | | | | **1.8 (±10)** |\n\n판정: **사람다움**.  \n자기소개서 장르상 자연스러운 공식 문체가 대부분이고, AI 특유의 과장·출처 없는 권위·챗봇 표현·바이럴 훅은 거의 보이지 않습니다.\n\n---\ntone: null\ntone_source: profile_only\ntone_evidence: []\ntone_confidence: null\n---",
  "scores": {
    "llm": {
      "overall": 1.8,
      "interpretation": "human"
    },
    "deterministic": {
      "overall": 20,
      "interpretation": "mostly human",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 5,
      "hotParagraphs": 1,
      "signalScore": 10.4,
      "bands": {
        "burstiness": {
          "low": 1,
          "mid": 0,
          "high": 0,
          "null": 4
        },
        "mattr": {
          "low": 0,
          "mid": 0,
          "high": 4,
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
    "preference": null
  }
}