@echo off
setlocal EnableExtensions

set "ROOT=%~dp0"
set "PYTHON=%ROOT%follei_backend\indic_tts_venv\Scripts\python.exe"
set "COMPOSE=%ROOT%docker-compose.yml"
set "PORT=8000"
set "NO_OPEN=0"
set "NO_PAUSE=0"

:parse_args
if "%~1"=="" goto :args_done
if /I "%~1"=="--no-open" set "NO_OPEN=1"
if /I "%~1"=="--no-pause" set "NO_PAUSE=1"
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

if not exist "%PYTHON%" (
  echo [ERROR] Canonical Python runtime was not found:
  echo         %PYTHON%
  goto :failed
)

if not exist "%ROOT%.env" (
  echo [ERROR] %ROOT%.env is missing. Follei cannot load its local settings.
  goto :failed
)

echo [1/7] Checking Python dependencies...
"%PYTHON%" -c "import fastapi,uvicorn,kafka,qdrant_client,pymongo,boto3,playwright" >nul 2>&1
if errorlevel 1 (
  echo [INFO] One or more dependencies are missing. Installing requirements...
  "%PYTHON%" -m pip install -r "%ROOT%requirements.txt"
  if errorlevel 1 (
    echo [ERROR] Python dependency installation failed.
    goto :failed
  )
) else (
  echo [OK] Python dependencies are available.
)

echo [2/7] Checking the website-ingestion browser runtime...
"%PYTHON%" -m playwright install chromium >nul
if errorlevel 1 (
  echo [WARN] Chromium could not be installed. Normal documents and server-rendered
  echo        websites still work; JavaScript-only websites may not.
) else (
  echo [OK] Chromium runtime is available.
)

echo [3/7] Starting local infrastructure...
where docker >nul 2>&1
if errorlevel 1 (
  echo [WARN] Docker CLI was not found. Checking for already-running services.
) else if exist "%COMPOSE%" (
  docker compose -p follei-backend-team -f "%COMPOSE%" up -d postgres redis qdrant minio ferretdb-postgres ferretdb zookeeper kafka
  if errorlevel 1 echo [WARN] Docker Compose reported an error; existing services will still be checked.
)

echo [4/7] Waiting for required stores and queues...
call :require_port "PostgreSQL" 55589 60
if errorlevel 1 goto :failed
call :require_port "Redis" 6379 60
if errorlevel 1 goto :failed
call :require_port "Kafka" 9092 90
if errorlevel 1 goto :failed
call :require_port "FerretDB" 27017 60
if errorlevel 1 goto :failed
call :require_port "Object storage" 9000 60
if errorlevel 1 goto :failed
call :require_url "Qdrant" "http://127.0.0.1:6333/readyz" 60
if errorlevel 1 goto :failed

echo [5/7] Applying the local database schema...
"%PYTHON%" -m app.database.bootstrap
if errorlevel 1 (
  echo [ERROR] Base database schema initialization failed.
  goto :failed
)
"%PYTHON%" -m alembic upgrade head
if errorlevel 1 (
  echo [ERROR] Database migration failed.
  goto :failed
)
echo [OK] Database schema is current.

echo [6/7] Starting API and all required workers...
set "OPEN_ARG="
if "%NO_OPEN%"=="1" set "OPEN_ARG=-NoOpen"
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\start_local_runtime.ps1" -Root "%ROOT:~0,-1%" -Python "%PYTHON%" -Port %PORT% %OPEN_ARG%
if errorlevel 1 goto :failed

echo [7/7] Startup complete.
echo.
echo Tenant console: http://127.0.0.1:%PORT%/tenant
echo Voice console:  http://127.0.0.1:%PORT%/user
echo API docs:       http://127.0.0.1:%PORT%/docs
echo Worker output:  visible in Windows Terminal tabs
echo Runtime state:  %ROOT%logs\runtime
echo.
if "%NO_PAUSE%"=="0" pause
endlocal
exit /b 0

:failed
echo.
echo ==========================================================
echo [FAILED] Follei did not start completely.
echo Review the error above and the Windows Terminal tabs.
echo ==========================================================
if "%NO_PAUSE%"=="0" pause
endlocal
exit /b 1

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