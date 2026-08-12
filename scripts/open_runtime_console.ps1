param(
    [Parameter(Mandatory = $true)][string]$Root,
    [switch]$Full
)

$ErrorActionPreference = "Stop"
$runtimeDir = Join-Path ([System.IO.Path]::GetFullPath($Root)) "logs\runtime"
$services = @(
    @{ Title = "Follei API"; Stem = "api" },
    @{ Title = "Indexing worker"; Stem = "indexing-worker" },
    @{ Title = "Knowledge sync"; Stem = "knowledge-sync-worker" },
    @{ Title = "Google Workspace"; Stem = "google-workspace-worker" },
    @{ Title = "Website ingestion"; Stem = "website-ingestion-worker" }
)
if ($Full) {
    $services += @(
        @{ Title = "Conversation analysis"; Stem = "analysis-worker" },
        @{ Title = "Lead scoring"; Stem = "lead-scoring-worker" },
        @{ Title = "Mail operations"; Stem = "mail-operations-worker" },
        @{ Title = "Flow execution"; Stem = "flow-execution-worker" },
        @{ Title = "HubSpot sync"; Stem = "hubspot-sync-worker" }
    )
}

$wt = Get-Command wt.exe -ErrorAction SilentlyContinue
if (-not $wt) {
    Write-Warning "Windows Terminal (wt.exe) is unavailable. Logs remain in $runtimeDir."
    return
}

$arguments = @("-w", "follei-runtime")
$first = $true
foreach ($service in $services) {
    $outLog = Join-Path $runtimeDir "$($service.Stem).out.log"
    $errLog = Join-Path $runtimeDir "$($service.Stem).err.log"
    foreach ($path in @($outLog, $errLog)) {
        if (-not (Test-Path -LiteralPath $path)) {
            New-Item -ItemType File -Path $path -Force | Out-Null
        }
    }
    if (-not $first) { $arguments += ";" }
    $first = $false
    $command = "Write-Host '=== $($service.Title) ==='; Write-Host 'stdout: $outLog'; Write-Host 'stderr: $errLog'; Get-Content -LiteralPath '$outLog','$errLog' -Tail 100 -Wait"
    $arguments += @(
        "new-tab", "--title", $service.Title,
        "powershell.exe", "-NoLogo", "-NoExit", "-NoProfile", "-Command", $command
    )
}

Start-Process -FilePath $wt.Source -ArgumentList $arguments | Out-Null

