@echo off
:: Launch the AWS S3 App
:: Works from any drive/folder — uses its own location to find the app

set "APP_DIR=%~dp0aws_download_app"
set "PYTHON=%USERPROFILE%\AppData\Local\miniconda3\python.exe"

echo Starting AWS S3 App...
echo The app will open in your browser at http://localhost:8501
echo Keep this window open while using the app.
echo Close this window to stop the app.
echo.

:: Start the Streamlit app using the explicit conda Python path
cd /d "%APP_DIR%"
"%PYTHON%" -m streamlit run app.py

pause
