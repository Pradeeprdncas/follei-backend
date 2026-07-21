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

# --- Detect Windows Terminal ---
$wtPaths = @(
    "$env:LOCALAPPDATA\Microsoft\WindowsApps\wt.exe",
    "wt.exe"
)
$wt = $null
foreach ($p in $wtPaths) {
    if (Get-Command $p -ErrorAction SilentlyContinue) {
        $wt = $p
        break
    }
}
if (-not $wt) {
    throw "Windows Terminal (wt.exe) not found. Install it from the Microsoft Store."
}

# --- Process tracking helpers ---
function Get-FolleiProcesses([string]$Marker) {
    @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.Name -like "python*" -and
        $_.CommandLine -and
        $_.CommandLine.IndexOf($Marker, [System.StringComparison]::OrdinalIgnoreCase) -ge 0
    })
}

function Get-FolleiPids([string]$Marker) {
    (Get-FolleiProcesses $Marker | ForEach-Object { $_.ProcessId })
}

# --- Tab definitions ---
$tabs = @(
    @{
        Name       = "Follei API"
        Marker     = "uvicorn app.main:app"
        Arguments  = @("-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "$Port")
        LogStem    = "api"
        Color      = "#2E7D32"
    },
    @{
        Name       = "Indexing worker"
        Marker     = "app.workers.indexing_consumer"
        Arguments  = @("-m", "app.workers.indexing_consumer")
        LogStem    = "indexing-worker"
        Color      = "#1565C0"
    },
    @{
        Name       = "Knowledge-sync worker"
        Marker     = "app.workers.knowledge_sync_consumer"
        Arguments  = @("-m", "app.workers.knowledge_sync_consumer")
        LogStem    = "knowledge-sync-worker"
        Color      = "#6A1B9A"
    },
    @{
        Name       = "Conversation-analysis worker"
        Marker     = "app.analysis.workers.analysis_worker"
        Arguments  = @("-m", "app.analysis.workers.analysis_worker")
        LogStem    = "analysis-worker"
        Color      = "#C62828"
    },
    @{
        Name       = "Lead-scoring worker"
        Marker     = "app.workers.lead_scoring_worker"
        Arguments  = @("-m", "app.workers.lead_scoring_worker")
        LogStem    = "lead-scoring-worker"
        Color      = "#EF6C00"
    }
)

# --- Check for already-running processes ---
$alreadyRunning = @()
foreach ($tab in $tabs) {
    $existing = Get-FolleiProcesses $tab.Marker
    if ($existing.Count -gt 0) {
        $ids = ($existing | ForEach-Object { $_.ProcessId }) -join ", "
        Write-Host "[OK] $($tab.Name) already running (PID $ids)."
        $alreadyRunning += $tab
    }
}

# --- Build Windows Terminal command string ---
# Build one single string that wt.exe receives. Semicolons separate tab commands.
$wtArgs = @()
$firstTab = $true

foreach ($tab in $tabs) {
    if ($alreadyRunning -contains $tab) { continue }

    $argLine = ($tab.Arguments | ForEach-Object {
        if ($_ -match '[\s&|<>^]') { '"' + ($_ -replace '"', '\"') + '"' } else { $_ }
    }) -join " "

    # The inner command for cmd /k. We use single quotes around the whole thing
    # and escape inner double quotes as \" for the wt.exe parser.
    $innerCmd = "title `"Follei - $($tab.Name)`" && cd /d `"$rootPath`" && `"$pythonPath`" -u $argLine & set FOLLEI_PROCESS_EXIT=!errorlevel! & title `"Follei - $($tab.Name) [EXITED !FOLLEI_PROCESS_EXIT!]`" & echo. & echo [EXITED] $($tab.Name) stopped with code !FOLLEI_PROCESS_EXIT!. Review the output above, then rerun start.bat."

    if (-not $firstTab) {
        $wtArgs += ";"
    }
    $firstTab = $false

    $wtArgs += 'new-tab'
    $wtArgs += '--title'
    $wtArgs += "`"$($tab.Name)`""
    $wtArgs += '--tabColor'
    $wtArgs += $tab.Color
    $wtArgs += '-d'
    $wtArgs += "`"$rootPath`""
    $wtArgs += 'cmd'
    $wtArgs += '/d'
    $wtArgs += '/v:on'
    $wtArgs += '/k'
    $wtArgs += "`"$innerCmd`""
}

# Join everything into ONE string with spaces
$wtCommandLine = $wtArgs -join " "

# --- Launch Windows Terminal ---
if ($wtArgs.Count -gt 0) {
    Write-Host "[INFO] Launching Windows Terminal with tabs..."
    Write-Host "[DEBUG] Command: wt $wtCommandLine"

    # CRITICAL: Pass the command as a SINGLE string argument, not an array.
    # wt.exe is a UWP app and PowerShell's array-to-string conversion breaks it.
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $wt
    $psi.Arguments = $wtCommandLine
    $psi.UseShellExecute = $true
    $psi.WorkingDirectory = $rootPath

    $proc = [System.Diagnostics.Process]::Start($psi)

    Start-Sleep -Seconds 3

    # Write sentinel PID
    if ($proc) {
        Set-Content -LiteralPath (Join-Path $runtimeDir "windows-terminal.pid") -Value $proc.Id
    }

    # Wait for python processes to appear
    $startupDeadline = (Get-Date).AddSeconds(30)
    foreach ($tab in $tabs) {
        if ($alreadyRunning -contains $tab) { continue }
        $found = $false
        while ((Get-Date) -lt $startupDeadline) {
            if ((Get-FolleiProcesses $tab.Marker).Count -gt 0) {
                $found = $true
                break
            }
            Start-Sleep -Milliseconds 500
        }
        if (-not $found) {
            throw "$($tab.Name) did not start inside its terminal tab."
        }
        $pids = Get-FolleiPids $tab.Marker
        Set-Content -LiteralPath (Join-Path $runtimeDir "$($tab.LogStem).pid") -Value ($pids -join "`n")
        Write-Host "[OK] $($tab.Name) started in terminal tab (PID $pids)."
    }
}

# --- Health check ---
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
    throw "API did not reach healthy state within 90 seconds. Review the Follei API terminal tab."
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
Write-Host "[OK] All output is visible in a single Windows Terminal window with color-coded tabs."

if (-not $NoOpen) {
    foreach ($url in $requiredPages) {
        Start-Process $url
    }
    Write-Host "[OK] Opened tenant and voice consoles in the default browser."
}