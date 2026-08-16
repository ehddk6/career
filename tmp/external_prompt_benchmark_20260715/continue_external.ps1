param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('company_codex', 'company_kakao')]
    [string]$Run
)

$root = Join-Path (Get-Location) 'tmp\external_prompt_benchmark_20260715\external_runs'
$runDir = Join-Path $root $Run
$prompt = @"
이 작업은 이전 실행의 후속 실행이다. 현재 디렉터리의 기존 산출물을 보존하고, 마지막 메시지에서 멈춘 단계 다음부터 끝까지 계속 수행하라.

목표:
- 기존 입력 input/ 디렉터리와 이전 산출물은 수정하거나 삭제하지 않는다.
- 외부 검색·브라우저·네트워크를 사용하지 않는다. input/ 안의 동결 공고, 경험 원장, 공식 조사 자료만 사용한다.
- 이전 단계에서 확인한 대상과 불일치 자료를 그대로 기록하되, 질문하거나 중단하지 말고 가능한 범위까지 진행한다.
- 확인할 수 없는 사항은 NEEDS_VERIFICATION/UNVERIFIED로 표시하고 제출용 사실로 사용하지 않는다.
- 회사조사 계약에 필요한 법인 식별, 출처 수준·기준일·조회일, claim 상태, 사업모델, 전략 실행, 경쟁·위험, 직무 연결, 반증 검증을 완료한다.
- company_research/final/ 아래에 최종 패킷, claim ledger, 금지 주장, 검증 보고서를 남긴다.
- 마지막 메시지에 완료 단계, 생성 파일, HARD_FAIL 여부, 남은 미검증 항목을 적는다.

이전 출력과 입력을 먼저 읽고 가장 최근에 완료된 단계의 다음 단계부터 시작하라. STEP 1~4가 완료되어 있으면 반드시 STEP 5부터 시작하라. 이번 실행에서는 `next_step`만 안내하고 멈추지 말고 남은 모든 단계와 `company_research/final/` 최종 패킷까지 끝내라. 공식 출처 원문이 input/에 없으면 해당 claim을 검증 불가로 남기고 `BLOCKED` 최종 보고서를 생성하되, 작업을 중단하지 말라. 동일한 단계에서 이미 완료된 파일은 재생성하지 말고 필요한 경우 새 파일명으로 보완하라.
"@

Set-Location $runDir
$log = Join-Path $runDir 'codex_continue.log'
$last = Join-Path $runDir 'last_message_continued.md'
$prompt | & codex exec --ephemeral --skip-git-repo-check --sandbox workspace-write --color never --cd $runDir --model gpt-5.6-sol --output-last-message $last - 1>> $log 2>&1
