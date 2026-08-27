@echo off
:: Thin, stable launcher for the AWS S3 App updater.
::
:: The actual update logic lives in update_app.py, not here. Because this
:: script updates itself as part of "git pull", keeping that logic in a
:: batch file is fragile (cmd.exe re-reads .bat files from disk line by
:: line as they execute, so the file changing mid-run can corrupt
:: execution). Python fully reads and compiles a script before running it,
:: so update_app.py is immune to that problem. This launcher itself should
:: rarely if ever need to change.

setlocal
set "REPO_DIR=%~dp0"
set "PYTHON=%USERPROFILE%\AppData\Local\miniconda3\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" -u "%REPO_DIR%update_app.py"
set "RC=%errorlevel%"
pause
exit /b %RC%
