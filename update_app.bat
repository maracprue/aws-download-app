@echo off
:: Updates the AWS S3 App from GitHub.
:: Run this any time to pull the latest version and refresh dependencies.
:: Works from any drive/folder — uses its own location as the repo root.

setlocal
set "REPO_DIR=%~dp0"
set "PYTHON=%USERPROFILE%\AppData\Local\miniconda3\python.exe"

cd /d "%REPO_DIR%"

if not exist "%REPO_DIR%.git" (
    echo This folder is not a git repository yet.
    echo Clone it first with:
    echo   git clone https://github.com/maracprue/aws-download-app.git
    pause
    exit /b 1
)

echo Checking for updates...
git pull --ff-only
if errorlevel 1 (
    echo.
    echo Update failed. You may have local changes that conflict with the update.
    echo Resolve them manually, then re-run this script.
    pause
    exit /b 1
)

echo.
echo Installing/updating Python dependencies...
if not exist "%PYTHON%" (
    echo Could not find Python at %PYTHON%
    echo Edit update_app.bat and set PYTHON to your Python interpreter path.
    pause
    exit /b 1
)

"%PYTHON%" -m pip install -r "%REPO_DIR%aws_download_app\requirements.txt" --upgrade

echo.
echo Update complete! Launch the app with launch_aws_app.bat
pause
