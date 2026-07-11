#!/usr/bin/env pwsh
# Career Pipeline self-test CI script

$ErrorActionPreference = "Stop"
$env:TMP = "C:\tmp"; $env:TEMP = "C:\tmp"

Write-Host "=== 1. Module imports ==="
python -c "import career_pipeline; print('OK')"

Write-Host ""
Write-Host "=== 2. Full test suite ==="
$output = python -m pytest tests/ --basetemp="C:\tmp\pytest-ci" -p no:cacheprovider --tb=short -q 2>&1 | Out-String
$lastLine = ($output -split "`n" | Where-Object { $_ -match 'passed|failed' } | Select-Object -Last 1)
Write-Host $lastLine

Write-Host ""
Write-Host "=== 3. SSRF defense ==="
python -c "
from career_pipeline.research_evidence import _official
allowed = ('khug.or.kr',)
cases = [
    ('https://www.khug.or.kr/posting', True),
    ('http://insecure.com', False),
    ('https://localhost/job', False),
    ('https://169.254.169.254/', False),
]
ok = all(_official(u, allowed) == e for u, e in cases)
print('SSRF defense:', 'OK' if ok else 'FAIL')
"

Write-Host ""
Write-Host "=== 4. Code metrics ==="
python -c "
from pathlib import Path
cp = list(Path('career_pipeline').glob('*.py'))
tests = list(Path('tests').glob('*.py'))
cp_lines = sum(sum(1 for _ in f.open(encoding='utf-8')) for f in cp)
test_lines = sum(sum(1 for _ in f.open(encoding='utf-8')) for f in tests)
print(f'Source: {len(cp)} .py, {cp_lines} lines')
print(f'Tests: {len(tests)} .py, {test_lines} lines')
"

Write-Host ""
Write-Host "=== All checks passed ==="
