STEP 1부터 STEP 15까지 완료했습니다. 최종 판정은 `INSUFFICIENT_EVIDENCE`입니다.

- 입력 62개 원본 해시 검증: PASS
- 카카오 대상 공식 자료: 0개
- 신용보증기금·한국도로공사서비스 자료: 대상 불일치로 제외
- 외부 네트워크 사용: 없음
- 활성 `HARD_FAIL`: 0건
- 미검증 차단 항목: 법인, 공식 공고, 사업부·직무, 재무 범위, 직무 적합성

주요 산출물:

- [최종 의사결정](C:/Users/ehddk/OneDrive/문서/취업/tmp/external_prompt_benchmark_20260715/external_runs/company_kakao/company_research/final/research_decision.json)
- [회사조사 보고서](C:/Users/ehddk/OneDrive/문서/취업/tmp/external_prompt_benchmark_20260715/external_runs/company_kakao/company_research/final/full_company_report.md)
- [지원 연결표](C:/Users/ehddk/OneDrive/문서/취업/tmp/external_prompt_benchmark_20260715/external_runs/company_kakao/company_research/final/application_bridge.md)
- [Claim Ledger](C:/Users/ehddk/OneDrive/문서/취업/tmp/external_prompt_benchmark_20260715/external_runs/company_kakao/company_research/final/claim_ledger.md)
- [금지 주장](C:/Users/ehddk/OneDrive/문서/취업/tmp/external_prompt_benchmark_20260715/external_runs/company_kakao/company_research/final/prohibited_claims.md)
- [최종 검증 보고서](C:/Users/ehddk/OneDrive/문서/취업/tmp/external_prompt_benchmark_20260715/external_runs/company_kakao/company_research/final/validation_report.md)
- [전체 원본 Manifest](C:/Users/ehddk/OneDrive/문서/취업/tmp/external_prompt_benchmark_20260715/external_runs/company_kakao/company_research/frozen/manifest.json)

`validate_packet.py` 검증 결과 필수 파일 60개, 입력 62개, 재무 계산 0건, 활성 HARD_FAIL 0건으로 PASS했습니다. 다음 단계에는 정확한 카카오 공식 채용공고와 채용 법인 정보가 필요합니다.

참고로 PDF 검사용 `tmp/pdfs/` 사본과 실패한 `__pycache__` 일부는 샌드박스 삭제 권한 거부로 남아 있으며 최종 manifest에서는 제외했습니다.