{
  "mode": "score",
  "format": "json",
  "overall": 40,
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
      "rawScore": 25,
      "weighted": 4.5
    },
    {
      "name": "style",
      "weight": 0.18,
      "detected": null,
      "rawScore": 27.8,
      "weighted": 5
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
    "overall": 40,
    "passed": false,
    "exitCode": 3
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | 0/6 | 0.0 | 0.0 |\n| language | 0.18 | 3/8 | 25.0 | 4.5 |\n| style | 0.18 | 2/6 | 27.8 | 5.0 |\n| communication | 0.13 | 0/4 | 0.0 | 0.0 |\n| filler | 0.08 | 2/4 | 33.3 | 2.7 |\n| structure | 0.15 | 2/5 | 26.7 | 4.0 |\n| viral-hook | 0.1 | 0/9 | 0.0 | 0.0 |\n| **Overall** | | | | **16.2 (±10)** |\n\n---\ntone: null\ntone_source: profile_only\ntone_evidence: []\ntone_confidence: null\n---",
  "scores": {
    "llm": {
      "overall": 16.2,
      "interpretation": "mostly human"
    },
    "deterministic": {
      "overall": 40,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 15,
      "hotParagraphs": 6,
      "signalScore": 24.7,
      "bands": {
        "burstiness": {
          "low": 6,
          "mid": 0,
          "high": 0,
          "null": 9
        },
        "mattr": {
          "low": 0,
          "mid": 0,
          "high": 14,
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
      "llmOverall": 16.2,
      "deterministicOverall": 40,
      "overall": 40
    }
  }
}