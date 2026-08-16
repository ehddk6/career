param(
    [Parameter(Mandatory = $true)]
    [string]$WorkspaceRoot,
    [Parameter(Mandatory = $true)]
    [string]$OutputPath
)

$ErrorActionPreference = 'Stop'
$workspace = (Resolve-Path -LiteralPath $WorkspaceRoot).Path
$inputRoot = Join-Path $workspace 'input'
if (-not (Test-Path -LiteralPath $inputRoot -PathType Container)) {
    throw "input directory not found: $inputRoot"
}

$files = Get-ChildItem -LiteralPath $inputRoot -Recurse -File |
    Sort-Object FullName |
    ForEach-Object {
        $relative = $_.FullName.Substring($workspace.Length + 1).Replace('\', '/')
        [ordered]@{
            path = $relative
            bytes = $_.Length
            sha256 = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        }
    }

$manifest = [ordered]@{
    schema_version = 1
    run_id = 'SOL-20260715-1537'
    data_package_id = 'SOL-DATA-EXT-001'
    data_package_version = '1.0'
    frozen_at = '2026-07-15T15:37:00+09:00'
    scope = [ordered]@{
        included_root = 'input/'
        excluded = @('career_pipeline_max_quality/', 'parent OneDrive paths', 'Downloads', 'internet')
        original_files_modified = $false
    }
    file_count = $files.Count
    files = @($files)
}

$parent = Split-Path -Parent $OutputPath
New-Item -ItemType Directory -Force -Path $parent | Out-Null
$json = $manifest | ConvertTo-Json -Depth 8
[IO.File]::WriteAllText($OutputPath, $json + "`n", [Text.UTF8Encoding]::new($false))

