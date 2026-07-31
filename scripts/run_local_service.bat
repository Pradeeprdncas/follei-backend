@echo off
setlocal EnableExtensions

set "SERVICE_NAME=%~1"
set "SERVICE_ROOT=%~2"
set "SERVICE_PYTHON=%~3"
shift
shift
shift

set "SERVICE_ARGS="
:collect_args
if "%~1"=="" goto run_service
set "SERVICE_ARGS=%SERVICE_ARGS% "%~1""
shift
goto collect_args

:run_service
title Follei - %SERVICE_NAME%
cd /d "%SERVICE_ROOT%"
if errorlevel 1 (
  echo [ERROR] Cannot enter project directory: %SERVICE_ROOT%
  exit /b 1
)

"%SERVICE_PYTHON%" -u %SERVICE_ARGS%
set "SERVICE_EXIT=%ERRORLEVEL%"

if "%SERVICE_EXIT%"=="0" (
  echo.
  echo [STOPPED] %SERVICE_NAME% exited cleanly.
) else if "%SERVICE_EXIT%"=="-1" (
  echo.
  echo [STOPPED] %SERVICE_NAME% was terminated by its terminal or operating system.
  echo This is a process-control exit, not a Gmail or mail-service response code.
) else (
  echo.
  echo [FAILED] %SERVICE_NAME% stopped with code %SERVICE_EXIT%.
  echo Review the output above, then rerun start.bat.
)

title Follei - %SERVICE_NAME% [EXITED %SERVICE_EXIT%]
endlocal & exit /b %SERVICE_EXIT%
