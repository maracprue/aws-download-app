# Resolves a real, working Python interpreter and runs update_app.py with it.
#
# This exists because a plain "python" on PATH can silently resolve to the
# Windows Store's placeholder alias (which just prints an install nag and
# exits) instead of a real interpreter, if the actual install location
# (e.g. a per-user Miniconda folder) isn't where we expect it to be. This
# script tries several real candidate locations/commands and verifies each
# one actually runs before using it, instead of guessing a single path.
#
# PowerShell scripts, like Python scripts, are fully parsed before they
# run, so this file is immune to the self-modification-during-git-pull
# corruption that affected the old all-batch update_app.bat (see comments
# in update_app.py for the full story).

$ErrorActionPreference = "Continue"
$repoDir = $PSScriptRoot

function Test-PythonCandidate($cmd) {
    try {
        & $cmd --version *> $null
        return ($LASTEXITCODE -eq 0)
    } catch {
        return $false
    }
}

$candidates = @(
    "$env:USERPROFILE\AppData\Local\miniconda3\python.exe",
    "$env:USERPROFILE\miniconda3\python.exe",
    "$env:USERPROFILE\Anaconda3\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
    "$env:LOCALAPPDATA\Programs\Python\Python310\python.exe",
    "C:\ProgramData\miniconda3\python.exe",
    "C:\ProgramData\Anaconda3\python.exe",
    "py",
    "python",
    "python3"
)

$python = $null
foreach ($c in $candidates) {
    if ($c -like "*\*" -and -not (Test-Path $c)) { continue }
    if (Test-PythonCandidate $c) { $python = $c; break }
}

if (-not $python) {
    Write-Host ""
    Write-Host "Could not find a working Python installation on this computer." -ForegroundColor Red
    Write-Host "(If a 'python' command opens the Microsoft Store, that's a placeholder," -ForegroundColor Yellow
    Write-Host " not a real Python -- it does not count.)" -ForegroundColor Yellow
    Write-Host ""
    Write-Host "Install Python -- e.g. Miniconda (https://docs.conda.io/en/latest/miniconda.html)"
    Write-Host "or python.org (https://www.python.org/downloads/, check 'Add python.exe to PATH')."
    Write-Host "Then re-run update_app.bat."
    Read-Host "Press Enter to exit"
    exit 1
}

& $python -u (Join-Path $repoDir "update_app.py")
$rc = $LASTEXITCODE
Read-Host "Press Enter to exit"
exit $rc
