#!/usr/bin/env python3
"""Reproducible financial gate for the frozen Kakao research packet.

No eligible target-company financial source exists in this package.  The
script therefore emits explicit zero-calculation artifacts.  It must not infer
values from off-target KODIT or Korea Expressway Service material.
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path


PACKAGE_ID = "CR-DATA-001"
PACKAGE_VERSION = "1.0"
REQUESTED_METRICS = [
    "revenue_growth",
    "operating_margin",
    "net_margin",
    "segment_or_region_mix",
    "rd_to_revenue",
    "capex_change",
    "operating_cash_flow",
    "free_cash_flow",
    "cash_and_debt_change",
    "inventory_and_receivables_change",
    "employee_change_and_revenue_per_employee",
    "customer_product_region_concentration",
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".", help="workspace root")
    args = parser.parse_args()
    root = Path(args.root).resolve()
    out = root / "company_research"
    validation = out / "validation"
    analysis = out / "analysis"
    validation.mkdir(parents=True, exist_ok=True)
    analysis.mkdir(parents=True, exist_ok=True)

    payload = {
        "company_data_package_id": PACKAGE_ID,
        "company_data_package_version": PACKAGE_VERSION,
        "status": "NOT_CALCULATED",
        "reason_code": "NO_ELIGIBLE_TARGET_FINANCIAL_SOURCE",
        "eligible_source_count": 0,
        "calculation_count": 0,
        "reporting_currency": "UNVERIFIED",
        "financial_cutoff_period": "UNVERIFIED",
        "consolidation_scope": "UNVERIFIED",
        "requested_metrics": [
            {"metric": metric, "status": "NEEDS_VERIFICATION", "value": None}
            for metric in REQUESTED_METRICS
        ],
        "excluded_sources": [
            "input/career_run: KODIT target mismatch",
            "input/직무기술서: Korea Expressway Service target mismatch",
        ],
        "hard_fail": False,
    }
    (validation / "financial_calculations.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )

    with (validation / "financial_calculations.csv").open(
        "w", encoding="utf-8", newline=""
    ) as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "metric_id",
                "metric",
                "period",
                "raw_value",
                "calculated_value",
                "unit",
                "formula",
                "source",
                "status",
                "reason_code",
            ],
        )
        writer.writeheader()
        for i, metric in enumerate(REQUESTED_METRICS, 1):
            writer.writerow(
                {
                    "metric_id": f"FIN-{i:03d}",
                    "metric": metric,
                    "period": "UNVERIFIED",
                    "raw_value": "",
                    "calculated_value": "",
                    "unit": "UNVERIFIED",
                    "formula": "NOT_APPLIED",
                    "source": "NONE",
                    "status": "NEEDS_VERIFICATION",
                    "reason_code": "NO_ELIGIBLE_TARGET_FINANCIAL_SOURCE",
                }
            )

    (analysis / "financial_evidence.md").write_text(
        """# Financial Evidence

- 데이터 패키지: `CR-DATA-001` v1.0
- 대상 회사 재무 원자료: 0개
- 연결·별도 범위: `UNVERIFIED`
- 기간·통화·단위: `UNVERIFIED`
- 계산 결과: 0건 (`NOT_CALCULATED`)

| Metric ID | 지표 | 기간 | 원자료 값 | 계산값 | 단위 | 계산식 | 출처 | 해석 가능 범위 |
|---|---|---|---:|---:|---|---|---|---|
| FIN-000 | 전체 요청 지표 | UNVERIFIED | - | - | UNVERIFIED | NOT_APPLIED | 없음 | 카카오 재무 해석 금지 |

KODIT career run과 한국도로공사서비스 직무기술서는 카카오 법인 재무 자료가 아니므로 계산 입력에서 제외했다. 수치가 없으므로 추정·환산·비율 계산을 하지 않았다.
""",
        encoding="utf-8",
        newline="\n",
    )

    (validation / "calculation_audit.md").write_text(
        """# Calculation Audit

- 데이터 패키지: `CR-DATA-001` v1.0
- 결과: `PASS_NO_CALCULATION`
- 적격 원자료: 0개
- 계산 수: 0건
- 기간·통화·단위·연결 범위 혼용: 없음
- 원자료와 다른 수치: 없음
- 조사 기준일 이후 자료 혼용: 없음

계산을 생략한 이유는 데이터 부족이다. 이는 재무 상태가 좋거나 나쁘다는 뜻이 아니다. 공식 공시를 확보한 뒤 연결·별도, 연간·분기, 통화·단위를 고정하고 같은 스크립트 계약을 확장해야 한다.
""",
        encoding="utf-8",
        newline="\n",
    )

    print(json.dumps({
        "status": "NOT_CALCULATED",
        "eligible_source_count": 0,
        "calculation_count": 0,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
