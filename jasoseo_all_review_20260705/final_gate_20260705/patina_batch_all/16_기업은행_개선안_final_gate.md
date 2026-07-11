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
      "rawScore": 0,
      "weighted": 0
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
    "overall": 36.4,
    "passed": false,
    "exitCode": 3
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | 없음 | 0.0 | 0.0 |\n| language | 0.18 | 없음 | 0.0 | 0.0 |\n| style | 0.18 | 약한 반복 연결 표현 Low 1 | 5.6 | 1.0 |\n| communication | 0.13 | 없음 | 0.0 | 0.0 |\n| filler | 0.08 | 약한 헤징 Low 1 | 8.3 | 0.7 |\n| structure | 0.15 | 자기소개서 문항별 구조 반복 Medium 2 | 13.3 | 2.0 |\n| viral-hook | 0.1 | 없음 | 0.0 | 0.0 |\n| **Overall** | | | | **3.7 (±10)** |\n\n판정: **사람다움**.  \n본문은 자기소개서 형식상 반복되는 기관명, 직무 연결, 경험-결과-입사 후 적용 구조가 보이지만, 과장된 홍보 문구나 챗봇 표현, 출처 없는 주장, 바이럴 훅은 거의 없습니다.\n\n```yaml\nphase_6:\n  ai_likeness_score: 3.7\n  interpretation: 사람다움\n  tone: null\n  tone_source: profile_only\n  tone_evidence: []\n  tone_confidence: null\n```",
  "scores": {
    "llm": {
      "overall": 3.7,
      "interpretation": "human"
    },
    "deterministic": {
      "overall": 36.4,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 11,
      "hotParagraphs": 4,
      "signalScore": 21.3,
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
      "llmOverall": 3.7,
      "deterministicOverall": 36.4,
      "overall": 36.4
    }
  }
}