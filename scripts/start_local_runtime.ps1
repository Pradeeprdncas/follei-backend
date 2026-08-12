param(
    [Parameter(Mandatory = $true)][string]$Root,
    [Parameter(Mandatory = $true)][string]$Python,
    [int]$Port = 8000,
    [switch]$NoOpen,
    [switch]$Full,
    [switch]$KeepRunning
)

$ErrorActionPreference = "Stop"
$rootPath = [System.IO.Path]::GetFullPath($Root).TrimEnd("\")
$pythonPath = [System.IO.Path]::GetFullPath($Python)
$runtimeDir = Join-Path $rootPath "logs\runtime"
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null

function Get-FolleiProcesses([string]$Marker) {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like "python*" -and $_.CommandLine -and
        $_.CommandLine.IndexOf($Marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    })
}

function Start-FolleiService([hashtable]$Service) {
    $existing = Get-FolleiProcesses $Service.Marker
    $pidFile = Join-Path $runtimeDir "$($Service.LogStem).pid"
    if ($KeepRunning -and $existing.Count -gt 0) {
        $ids = ($existing | ForEach-Object { $_.ProcessId })
        Set-Content -LiteralPath $pidFile -Value ($ids -join "`n")
        Write-Host "[OK] $($Service.Name) already running (PID $($ids -join ', '))."
        return
    }
    if ($existing.Count -gt 0) {
        $ids = ($existing | ForEach-Object { $_.ProcessId })
        Write-Host "[INFO] Restarting $($Service.Name) (stopping PID $($ids -join ', ')) so code and .env changes are loaded."
        foreach ($process in $existing) {
            Stop-Process -Id $process.ProcessId -Force -ErrorAction SilentlyContinue
        }
        Remove-Item -LiteralPath $pidFile -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 1
    }

    $outLog = Join-Path $runtimeDir "$($Service.LogStem).out.log"
    $errLog = Join-Path $runtimeDir "$($Service.LogStem).err.log"
    $process = Start-Process -FilePath $pythonPath `
        -ArgumentList $Service.Arguments `
        -WorkingDirectory $rootPath `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -PassThru
    Start-Sleep -Seconds 1
    if ($process.HasExited) {
        throw "$($Service.Name) exited during startup. Review $errLog."
    }
    Set-Content -LiteralPath $pidFile -Value $process.Id
    Write-Host "[OK] $($Service.Name) started (PID $($process.Id))."
}

$services = @(
    @{ Name="Follei API"; Marker="app.main:app"; LogStem="api"; Arguments=@("-u", "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port") },
    @{ Name="Indexing worker"; Marker="app.workers.indexing_consumer"; LogStem="indexing-worker"; Arguments=@("-u", "-m", "app.workers.indexing_consumer") },
    @{ Name="Knowledge-sync worker"; Marker="app.workers.knowledge_sync_consumer"; LogStem="knowledge-sync-worker"; Arguments=@("-u", "-m", "app.workers.knowledge_sync_consumer") },
    @{ Name="Google Workspace worker"; Marker="app.workers.google_workspace_worker"; LogStem="google-workspace-worker"; Arguments=@("-u", "-m", "app.workers.google_workspace_worker") },
    @{ Name="Website ingestion worker"; Marker="app.workers.website_ingestion_worker"; LogStem="website-ingestion-worker"; Arguments=@("-u", "-m", "app.workers.website_ingestion_worker") }
)

if ($Full) {
    $services += @(
        @{ Name="Conversation-analysis worker"; Marker="app.analysis.workers.analysis_worker"; LogStem="analysis-worker"; Arguments=@("-u", "-m", "app.analysis.workers.analysis_worker") },
        @{ Name="Lead-scoring worker"; Marker="app.workers.lead_scoring_worker"; LogStem="lead-scoring-worker"; Arguments=@("-u", "-m", "app.workers.lead_scoring_worker") },
        @{ Name="Mail operations worker"; Marker="app.workers.mail_operations_worker"; LogStem="mail-operations-worker"; Arguments=@("-u", "-m", "app.workers.mail_operations_worker") },
        @{ Name="Flow execution worker"; Marker="app.workers.flow_execution_worker"; LogStem="flow-execution-worker"; Arguments=@("-u", "-m", "app.workers.flow_execution_worker") },
        @{ Name="HubSpot sync worker"; Marker="app.workers.hubspot_sync_worker"; LogStem="hubspot-sync-worker"; Arguments=@("-u", "-m", "app.workers.hubspot_sync_worker") }
    )
}

foreach ($service in $services) {
    Start-FolleiService $service
}

$healthUrl = "http://127.0.0.1:$Port/health/"
$deadline = (Get-Date).AddSeconds(90)
$health = $null
do {
    try {
        $health = Invoke-RestMethod -Uri $healthUrl -TimeoutSec 4
        if ($health.status -eq "healthy") { break }
    } catch { $health = $null }
    Start-Sleep -Seconds 1
} while ((Get-Date) -lt $deadline)

if (-not $health -or $health.status -ne "healthy") {
    throw "API did not reach healthy state within 90 seconds. Review logs\runtime\api.err.log."
}

Write-Host "[OK] Follei core runtime is healthy. Logs and PID files: $runtimeDir"
foreach ($service in $services) {
    $pidFile = Join-Path $runtimeDir "$($service.LogStem).pid"
    $pidValue = Get-Content -LiteralPath $pidFile -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $pidValue -or -not (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)) {
        throw "$($service.Name) exited during startup. Review logs\runtime\$($service.LogStem).err.log."
    }
}
if (-not $NoOpen) {
    Start-Process "http://127.0.0.1:$Port/docs"
}
