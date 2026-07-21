param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Python,
    [int]$Port = 8000,
    [switch]$NoOpen
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
$pythonPath = [System.IO.Path]::GetFullPath($Python)
$runtimeDir = Join-Path $rootPath "logs\runtime"
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

function Get-FolleiProcesses([string]$Marker) {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like "python*" -and
        $_.CommandLine -and
        $_.CommandLine.IndexOf($Marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    })
}

function Start-FolleiProcess {
    param(
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Marker,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [Parameter(Mandatory = $true)][string]$LogStem
    )

    $existing = Get-FolleiProcesses $Marker
    if ($existing.Count -gt 0) {
        $ids = ($existing | ForEach-Object { $_.ProcessId }) -join ", "
        Write-Host "[OK] $Name already running (PID $ids)."
        return
    }

    $argumentLine = ($Arguments | ForEach-Object {
        if ($_ -match '[\s&|<>^]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join " "
    $terminalCommand = "title Follei - $Name && cd /d `"$rootPath`" && `"$pythonPath`" -u $argumentLine & set FOLLEI_PROCESS_EXIT=!errorlevel! & title Follei - $Name [EXITED !FOLLEI_PROCESS_EXIT!] & echo. & echo [EXITED] $Name stopped with code !FOLLEI_PROCESS_EXIT!. Review the output above, then rerun start.bat."
    $process = Start-Process -FilePath $env:ComSpec `
        -ArgumentList @("/d", "/v:on", "/k", $terminalCommand) `
        -WorkingDirectory $rootPath `
        -WindowStyle Normal `
        -PassThru
    Set-Content -LiteralPath (Join-Path $runtimeDir "$LogStem.pid") -Value $process.Id
    Start-Sleep -Seconds 1
    if ($process.HasExited) {
        throw "$Name terminal exited during startup."
    }
    if ((Get-FolleiProcesses $Marker).Count -eq 0) {
        throw "$Name did not start inside its terminal window."
    }
    Write-Host "[OK] $Name started in a visible terminal (terminal PID $($process.Id))."
}

Start-FolleiProcess -Name "Indexing worker" `
    -Marker "app.workers.indexing_consumer" `
    -Arguments @("-m", "app.workers.indexing_consumer") `
    -LogStem "indexing-worker"

Start-FolleiProcess -Name "Knowledge-sync worker" `
    -Marker "app.workers.knowledge_sync_consumer" `
    -Arguments @("-m", "app.workers.knowledge_sync_consumer") `
    -LogStem "knowledge-sync-worker"

Start-FolleiProcess -Name "Conversation-analysis worker" `
    -Marker "app.analysis.workers.analysis_worker" `
    -Arguments @("-m", "app.analysis.workers.analysis_worker") `
    -LogStem "analysis-worker"

Start-FolleiProcess -Name "Lead-scoring worker" `
    -Marker "app.workers.lead_scoring_worker" `
    -Arguments @("-m", "app.workers.lead_scoring_worker") `
    -LogStem "lead-scoring-worker"

Start-FolleiProcess -Name "Follei API" `
    -Marker "uvicorn app.main:app" `
    -Arguments @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") `
    -LogStem "api"

$healthUrl = "http://127.0.0.1:$Port/health/"
$deadline = (Get-Date).AddSeconds(90)
$lastHealth = $null
do {
    try {
        $lastHealth = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 4
        if ($lastHealth.status -eq "healthy") { break }
    } catch {
        $lastHealth = $null
    }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)

if (-not $lastHealth -or $lastHealth.status -ne "healthy") {
    throw "API did not reach healthy state within 90 seconds. Review the visible Follei API terminal."
}

$requiredPages = @(
    "http://127.0.0.1:$Port/tenant",
    "http://127.0.0.1:$Port/user"
)
foreach ($url in $requiredPages) {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $url -TimeoutSec 5
    if ($response.StatusCode -ne 200) {
        throw "Required page returned HTTP $($response.StatusCode): $url"
    }
}

Write-Host "[OK] API health is green and both interfaces return HTTP 200."
Write-Host "[OK] BANT/MEDDIC run in the API voice pipeline; analysis and lead-score persistence workers are active."
Write-Host "[OK] API and worker output remains visible in separately titled terminal windows."

if (-not $NoOpen) {
    foreach ($url in $requiredPages) {
        Start-Process $url
    }
    Write-Host "[OK] Opened tenant and voice consoles in the default browser."
}
