@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "PYTHON="
set "BOOTSTRAP_PYTHON="
set "COMPOSE=%ROOT%docker-compose.yml"
set "PORT=8000"
set "NO_OPEN=0"
set "NO_PAUSE=0"
set "FULL_PROFILE=0"
set "NO_INFRA=0"
set "CHECK_ONLY=0"
set "INSTALL_BROWSER=0"

:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="--no-open" set "NO_OPEN=1"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
if /I "%~1"=="--full" set "FULL_PROFILE=1"
if /I "%~1"=="--no-infra" set "NO_INFRA=1"
if /I "%~1"=="--check" set "CHECK_ONLY=1"
if /I "%~1"=="--install-browser" set "INSTALL_BROWSER=1"
if /I "%~1"=="--skip-browser" set "INSTALL_BROWSER=0"
if /I "%~1"=="--help" goto :help
shift
goto :parse_args
:args_done

cd /d "%ROOT%"
echo.
echo ==========================================================
echo                 Follei local startup
echo ==========================================================
echo Root: %ROOT%
echo.

call :find_python
if not defined PYTHON (
  echo [ERROR] Python 3.10 or newer was not found.
  echo         Install Python from https://www.python.org/downloads/windows/
  echo         and select "Add Python to PATH", then run start.bat again.
  goto :failed
)
echo [OK] Using Python: %PYTHON%

if not exist "%ROOT%.env" (
  echo [ERROR] %ROOT%.env is missing. Follei cannot load its local settings.
  goto :failed
)

if not exist "%ROOT%alembic.ini" (
  echo [ERROR] alembic.ini is missing. Database migrations cannot be applied.
  goto :failed
)

if not exist "%ROOT%scripts\start_local_runtime.ps1" (
  echo [ERROR] scripts\start_local_runtime.ps1 is missing. Services cannot be started.
  goto :failed
)
if not exist "%ROOT%requirements-core.txt" (
  echo [ERROR] requirements-core.txt is missing.
  goto :failed
)

echo [1/7] Checking Python dependencies...
"%PYTHON%" -c "import alembic,fastapi,psycopg2,uvicorn,kafka,qdrant_client,pymongo,boto3,redis; from app.main import app; from app.workers.indexing_consumer import IndexingWorker; from app.workers.knowledge_sync_consumer import KnowledgeSyncWorker; from app.workers.google_workspace_worker import GoogleWorkspaceWorker; from app.workers.website_ingestion_worker import WebsiteIngestionWorker" >nul 2>&1
if errorlevel 1 (
  echo [INFO] One or more dependencies are missing. Installing requirements...
  "%PYTHON%" -m pip install -r "%ROOT%requirements-core.txt"
  if errorlevel 1 (
    echo [ERROR] Python dependency installation failed.
    goto :failed
  )
  if "%FULL_PROFILE%"=="1" "%PYTHON%" -m pip install -r "%ROOT%requirements-optional-ai.txt"
) else (
  echo [OK] Python dependencies are available.
)
if "%FULL_PROFILE%"=="1" (
  "%PYTHON%" -c "import torch,transformers,peft,soundfile,librosa,noisereduce,gtts" >nul 2>&1
  if errorlevel 1 "%PYTHON%" -m pip install -r "%ROOT%requirements-optional-ai.txt"
  if errorlevel 1 goto :failed
)

echo [2/7] Checking the website-ingestion browser runtime...
if "%INSTALL_BROWSER%"=="1" (
  "%PYTHON%" -m playwright install chromium >nul
  if errorlevel 1 (
    echo [WARN] Chromium could not be installed. Normal documents and server-rendered
    echo        websites still work; JavaScript-only websites may not.
  ) else (
    echo [OK] Chromium runtime is available.
  )
) else (
  echo [SKIP] Browser installation skipped. Use --install-browser for JavaScript-heavy sites.
)

if "%CHECK_ONLY%"=="1" (
  call :print_service_plan
  echo [OK] Runtime check passed; nothing was started.
  goto :success
)

echo [3/7] Starting local infrastructure...
call :infrastructure_ready_now
if not errorlevel 1 (
  echo [OK] Required infrastructure is already reachable; skipping Docker Compose.
  goto :infrastructure_started
)
if "%NO_INFRA%"=="1" (
  echo [SKIP] Docker Compose disabled by --no-infra.
) else (
  where docker >nul 2>&1
  if errorlevel 1 (
    echo [WARN] Docker CLI was not found. Checking for already-running services.
  ) else if exist "%COMPOSE%" (
    docker compose -p follei-backend-team -f "%COMPOSE%" up -d postgres redis qdrant minio ferretdb-postgres ferretdb zookeeper kafka
    if errorlevel 1 echo [WARN] Docker Compose reported an error; existing services will still be checked.
  )
)

:infrastructure_started
echo [4/7] Waiting for required stores and queues...
call :require_port "PostgreSQL" 55589 60
if errorlevel 1 goto :failed
"%PYTHON%" "%ROOT%scripts\ensure_local_postgres_access.py"
if errorlevel 1 (
  echo [ERROR] PostgreSQL credentials could not be reconciled with DATABASE_URL.
  goto :failed
)
call :require_port "Redis" 6379 60
if errorlevel 1 goto :failed
"%PYTHON%" "%ROOT%scripts\wait_for_kafka.py" --timeout 120
if errorlevel 1 (
  echo [ERROR] Kafka did not become ready for producer and consumer connections.
  goto :failed
)
call :require_port "FerretDB" 27017 60
if errorlevel 1 goto :failed
call :require_port "Object storage" 9000 60
if errorlevel 1 goto :failed
call :require_url "Qdrant" "http://127.0.0.1:6333/readyz" 60
if errorlevel 1 goto :failed

echo [5/7] Reconciling the local database schema...
"%PYTHON%" -m app.database.bootstrap
if errorlevel 1 (
  echo [ERROR] Database schema initialization or migration failed.
  goto :failed
)
echo [OK] Database schema is current.

echo [6/7] Starting the lightweight core services...
set "OPEN_ARG="
if "%NO_OPEN%"=="1" set "OPEN_ARG=-NoOpen"
set "FULL_ARG="
if "%FULL_PROFILE%"=="1" set "FULL_ARG=-Full"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start_local_runtime.ps1" -Root "%ROOT:~0,-1%" -Python "%PYTHON%" -Port %PORT% %OPEN_ARG% %FULL_ARG%
if errorlevel 1 goto :failed

echo [7/7] Startup complete.
echo.
call :print_service_plan
echo API docs:       http://127.0.0.1:%PORT%/docs
echo Worker output:  %ROOT%logs\runtime
echo Runtime state:  %ROOT%logs\runtime
echo.
:success
if "%NO_PAUSE%"=="0" pause
endlocal
exit /b 0

:failed
echo.
echo ==========================================================
echo [FAILED] Follei did not start completely.
echo Review the error above and logs\runtime\*.err.log.
echo ==========================================================
if "%NO_PAUSE%"=="0" pause
endlocal
exit /b 1

:help
echo Usage: start.bat [--full] [--no-infra] [--check] [--install-browser] [--no-open] [--no-pause]
echo.
echo   default         API + indexing + knowledge sync + Google sync + website crawl.
echo   --full          Also start analysis, lead scoring, mail, flow, and HubSpot workers.
echo   --no-infra      Use externally managed stores and Kafka.
echo   --check         Validate imports and print the service plan without starting.
echo   --install-browser  Install Playwright Chromium for JavaScript-heavy sites.
echo   --no-open       Do not open the API documentation after startup.
echo   --no-pause      Do not wait for a key press when the script finishes.
echo   --skip-browser  Backward-compatible alias for the light default.
endlocal
exit /b 0

:print_service_plan
echo Core services:
echo   1. API - OAuth, validation, onboarding checks, retrieval
echo   2. Indexing worker - parse, classify, chunk, embed
echo   3. Knowledge-sync worker - FerretDB/Qdrant projection
echo   4. Google Workspace sync worker
echo   5. Website ingestion worker
if "%FULL_PROFILE%"=="1" echo Optional full profile: analysis, lead scoring, mail, flows, HubSpot
exit /b 0

:find_python
rem Prefer project-local environments. They make startup portable and prevent
rem package installations from modifying the user's global Python setup.
if exist "%ROOT%follei_backend\indic_tts_venv\Scripts\python.exe" (
  set "PYTHON=%ROOT%follei_backend\indic_tts_venv\Scripts\python.exe"
  exit /b 0
)
if exist "%ROOT%.venv\Scripts\python.exe" (
  set "PYTHON=%ROOT%.venv\Scripts\python.exe"
  exit /b 0
)
if exist "%ROOT%venv\Scripts\python.exe" (
  set "PYTHON=%ROOT%venv\Scripts\python.exe"
  exit /b 0
)

rem Resolve a real interpreter path. `py -3` works even when `python` is not
rem on PATH; the second command covers Python installations without py.exe.
for /f "usebackq delims=" %%P in (`py -3 -c "import sys; print(sys.executable)" 2^>nul`) do if not defined BOOTSTRAP_PYTHON set "BOOTSTRAP_PYTHON=%%P"
if not defined BOOTSTRAP_PYTHON for /f "usebackq delims=" %%P in (`python -c "import sys; print(sys.executable)" 2^>nul`) do if not defined BOOTSTRAP_PYTHON set "BOOTSTRAP_PYTHON=%%P"
if not defined BOOTSTRAP_PYTHON exit /b 1

echo [INFO] Creating local Python environment: %ROOT%.venv
"%BOOTSTRAP_PYTHON%" -m venv "%ROOT%.venv"
if errorlevel 1 (
  echo [WARN] Could not create .venv. Falling back to the detected Python runtime.
  set "PYTHON=%BOOTSTRAP_PYTHON%"
  exit /b 0
)
set "PYTHON=%ROOT%.venv\Scripts\python.exe"
exit /b 0

:infrastructure_ready_now
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ports=@(55589,6379,9092,27017,9000,6333); foreach($port in $ports){try{$client=[System.Net.Sockets.TcpClient]::new();$task=$client.ConnectAsync('127.0.0.1',$port);if(-not ($task.Wait(750)-and $client.Connected)){$client.Dispose();exit 1};$client.Dispose()}catch{exit 1}};exit 0" >nul 2>&1
exit /b %errorlevel%

:require_port
set "CHECK_NAME=%~1"
set "CHECK_PORT=%~2"
set "CHECK_SECONDS=%~3"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(%CHECK_SECONDS%); do { try { $c=[System.Net.Sockets.TcpClient]::new(); $task=$c.ConnectAsync('127.0.0.1',%CHECK_PORT%); if($task.Wait(750) -and $c.Connected){$c.Dispose();exit 0};$c.Dispose() } catch {}; Start-Sleep -Milliseconds 750 } while((Get-Date)-lt $deadline); exit 1" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] %CHECK_NAME% did not become reachable on port %CHECK_PORT%.
  exit /b 1
)
echo [OK] %CHECK_NAME% is reachable on port %CHECK_PORT%.
exit /b 0

:require_url
set "CHECK_NAME=%~1"
set "CHECK_URL=%~2"
set "CHECK_SECONDS=%~3"
powershell -NoProfile -ExecutionPolicy Bypass -Command "$deadline=(Get-Date).AddSeconds(%CHECK_SECONDS%); do { try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%CHECK_URL%'; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 400){exit 0} } catch {}; Start-Sleep -Milliseconds 750 } while((Get-Date)-lt $deadline); exit 1" >nul 2>&1
if errorlevel 1 (
  echo [ERROR] %CHECK_NAME% did not become ready: %CHECK_URL%
  exit /b 1
)
echo [OK] %CHECK_NAME% is ready.
exit /b 0
