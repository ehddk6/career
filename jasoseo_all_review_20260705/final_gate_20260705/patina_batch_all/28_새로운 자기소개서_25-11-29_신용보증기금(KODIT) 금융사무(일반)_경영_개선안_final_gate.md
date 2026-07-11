{
  "mode": "score",
  "format": "json",
  "overall": 38.5,
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
      "detected": 0,
      "rawScore": 0,
      "weighted": 0
    },
    {
      "name": "filler",
      "weight": 0.08,
      "detected": null,
      "rawScore": 25,
      "weighted": 2
    },
    {
      "name": "structure",
      "weight": 0.15,
      "detected": null,
      "rawScore": 40,
      "weighted": 6
    },
    {
      "name": "viral-hook",
      "weight": 0.1,
      "detected": 0,
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
    "overall": 38.5,
    "passed": false,
    "exitCode": 3
  },
  "output": "| Category | Weight | Detected | Raw Score | Weighted |\n|----------|--------|----------|-----------|----------|\n| content | 0.18 | 1 (#3 Low) | 5.6 | 1.0 |\n| language | 0.18 | 3 (#7 Medium, #8 Low, #10 Low) | 16.7 | 3.0 |\n| style | 0.18 | 2 (#13 Medium, #18 Medium) | 22.2 | 4.0 |\n| communication | 0.13 | 0 | 0.0 | 0.0 |\n| filler | 0.08 | 2 (#22 Low, #23 Medium) | 25.0 | 2.0 |\n| structure | 0.15 | 3 (#25 High, #26 Medium, #27 Low) | 40.0 | 6.0 |\n| viral-hook | 0.1 | 0 | 0.0 | 0.0 |\n| **Overall** | | | | **16.0 (±10)** |\n\n```yaml\nphase_6:\n  tone: null\n  tone_source: profile_only\n  tone_evidence: []\n  tone_confidence: null\n```",
  "scores": {
    "llm": {
      "overall": 16,
      "interpretation": "mostly human"
    },
    "deterministic": {
      "overall": 38.5,
      "interpretation": "mixed",
      "skipped": false,
      "skipReason": null,
      "paragraphCount": 13,
      "hotParagraphs": 5,
      "signalScore": 18.1,
      "bands": {
        "burstiness": {
          "low": 5,
          "mid": 0,
          "high": 2,
          "null": 6
        },
        "mattr": {
          "low": 0,
          "mid": 0,
          "high": 12,
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
      "llmOverall": 16,
      "deterministicOverall": 38.5,
      "overall": 38.5
    }
  }
}