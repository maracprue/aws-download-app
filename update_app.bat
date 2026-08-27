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
::
:: Finding a real Python interpreter is delegated to update_app.ps1 (also
:: immune to self-modification corruption) because a single guessed path
:: with a bare "python" fallback isn't reliable across machines -- on some
:: computers "python" resolves to the Windows Store's placeholder alias
:: instead of a real interpreter.

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0update_app.ps1"
exit /b %errorlevel%
