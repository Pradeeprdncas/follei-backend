@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "PYTHON=%ROOT%follei_backend\indic_tts_venv\Scripts\python.exe"
set "PORT=8000"

rem Connection settings, credentials, and API keys are loaded from .env.
rem Do not override them here: environment variables would take precedence over .env.

cd /d "%ROOT%"
echo.
echo ========================================
echo        Follei startup
echo ========================================
echo Root: %ROOT%

if not exist "%PYTHON%" (
  echo [ERROR] Python runtime not found:
  echo         %PYTHON%
  echo Create the canonical venv before starting Follei.
  pause
  exit /b 1
)

if exist "%ROOT%requirements.txt" (
  echo [INFO] Installing/updating Python dependencies from requirements.txt...
  "%PYTHON%" -m pip install -r "%ROOT%requirements.txt"
  if errorlevel 1 (
    echo [ERROR] Dependency installation failed. Follei was not started.
    pause
    exit /b 1
  )
)

echo [INFO] Ensuring the bounded website crawler Chromium runtime exists...
"%PYTHON%" -m playwright install chromium
if errorlevel 1 (
  echo [WARN] Playwright Chromium is unavailable. Server-rendered websites can still be ingested,
  echo        but JavaScript-only websites will require this runtime.
)

set "COMPOSE_FILE="
if exist "%ROOT%docker-compose.yml" set "COMPOSE_FILE=%ROOT%docker-compose.yml"
if not defined COMPOSE_FILE if exist "%ROOT%follei_backend\follei\docker-compose.yml" set "COMPOSE_FILE=%ROOT%follei_backend\follei\docker-compose.yml"

if defined COMPOSE_FILE (
  echo [INFO] Starting Docker services from:
  echo        %COMPOSE_FILE%
  docker compose -p follei-backend-team -f "%COMPOSE_FILE%" up -d postgres redis qdrant minio ferretdb-postgres ferretdb zookeeper kafka
  if errorlevel 1 (
    echo [WARN] Docker Compose could not start all services.
    echo        Continuing so existing services can still be used.
  )
) else (
  echo [INFO] No Compose file found in the active checkout.
  echo        Using already-running Docker services.
)

call :check_url "Qdrant" "http://localhost:6333/readyz"
call :check_port "FerretDB" 27017
call :check_port "PostgreSQL" 55589
call :check_port "Redis" 6379
call :check_port "Kafka" 9092
call :check_port "Object storage" 9000

echo [INFO] Ensuring the local base database schema exists...
"%PYTHON%" -m app.database.bootstrap
if errorlevel 1 (
  echo [ERROR] Base database schema initialization failed. Follei was not started.
  pause
  exit /b 1
)

echo [INFO] Applying non-destructive database migrations...
"%PYTHON%" -m alembic upgrade head
if errorlevel 1 (
  echo [ERROR] Database migration failed. Follei was not started.
  pause
  exit /b 1
)

for /f "tokens=5" %%P in ('netstat -ano ^| findstr /R /C:":%PORT% .*LISTENING"') do (
  echo [WARN] Port %PORT% is already in use by PID %%P. The API may already be running.
  goto :after_port_check
)
:after_port_check

call :require_port "Kafka" 9092
if errorlevel 1 (
  echo [ERROR] Kafka is required for queued indexing. Follei workers were not started.
  pause
  exit /b 1
)

echo [INFO] Starting Follei indexing worker...
start "Follei Indexing Worker" /D "%ROOT%" "%PYTHON%" -m app.workers.indexing_consumer
echo [INFO] Starting Follei knowledge sync worker...
start "Follei Knowledge Sync Worker" /D "%ROOT%" "%PYTHON%" -m app.workers.knowledge_sync_consumer

echo [INFO] Starting Follei API on port %PORT%...
start "Follei API" /D "%ROOT%" "%PYTHON%" -m uvicorn app.main:app --reload --port %PORT%

timeout /t 3 /nobreak >nul
call :check_url "Follei API" "http://localhost:%PORT%/health/"

echo.
echo Follei startup command completed.
echo API:     http://localhost:%PORT%
echo Docs:    http://localhost:%PORT%/docs
echo Chat:    http://localhost:%PORT%/chat/
echo Review:  http://localhost:%PORT%/knowledge/review/drafts
endlocal
exit /b 0

:check_url
set "CHECK_NAME=%~1"
set "CHECK_URL=%~2"
for /l %%N in (1,1,10) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "try { $r=Invoke-WebRequest -UseBasicParsing -TimeoutSec 2 '%CHECK_URL%'; if($r.StatusCode -ge 200 -and $r.StatusCode -lt 500){ exit 0 } } catch {} ; exit 1" >nul 2>&1
  if not errorlevel 1 (
    echo [OK] %CHECK_NAME% ready: %CHECK_URL%
    exit /b 0
  )
  timeout /t 1 /nobreak >nul
)
echo [WARN] %CHECK_NAME% not reachable yet: %CHECK_URL%
exit /b 0

:check_port
set "CHECK_NAME=%~1"
set "CHECK_PORT=%~2"
powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Test-NetConnection localhost -Port %CHECK_PORT% -WarningAction SilentlyContinue).TcpTestSucceeded){exit 0}else{exit 1}" >nul 2>&1
if not errorlevel 1 (
  echo [OK] %CHECK_NAME% port %CHECK_PORT% reachable
) else (
  echo [WARN] %CHECK_NAME% port %CHECK_PORT% not reachable
)
exit /b 0

:require_port
set "CHECK_NAME=%~1"
set "CHECK_PORT=%~2"
for /l %%N in (1,1,20) do (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "if((Test-NetConnection localhost -Port %CHECK_PORT% -WarningAction SilentlyContinue).TcpTestSucceeded){exit 0}else{exit 1}" >nul 2>&1
  if not errorlevel 1 exit /b 0
  timeout /t 1 /nobreak >nul
)
echo [ERROR] %CHECK_NAME% port %CHECK_PORT% did not become reachable.
exit /b 1
