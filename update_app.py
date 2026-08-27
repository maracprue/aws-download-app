"""
Update helper for the AWS S3 App.

Run via update_app.bat (double-click, or from a terminal). Safely updates
this local checkout from GitHub:

  1. Detects local changes and stashes them if present, so "git pull" can't
     fail just because of an uncommitted tweak.
  2. Pulls the latest commit with --ff-only (never merges/rebases, so it
     never invents a merge commit or silently combines histories).
  3. Reapplies any stashed local changes on top of the update.
  4. Reinstalls/upgrades Python dependencies from requirements.txt.

Safe to re-run any time. If anything goes wrong partway through, your local
changes are preserved in `git stash list` -- the printed message tells you
how to recover them.

NOTE: this logic intentionally lives in a .py file rather than directly in
update_app.bat. Since this script updates itself as part of "git pull",
and batch files are re-read from disk line-by-line as they execute, a
self-updating .bat can get its own file rewritten out from under the
running interpreter mid-script and misbehave. Python scripts are fully
read and compiled before execution starts, so this file can safely update
itself with no special handling.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent

# Candidate Python interpreters to use for reinstalling dependencies,
# in preference order.
_PYTHON_CANDIDATES = [
    Path.home() / "AppData" / "Local" / "miniconda3" / "python.exe",
    Path(sys.executable),
]


def _run(cmd: list[str]) -> subprocess.CompletedProcess:
    print(f"$ {' '.join(cmd)}")
    return subprocess.run(cmd, cwd=REPO_DIR)


def _has_local_changes() -> bool:
    unstaged = _run(["git", "diff", "--quiet"]).returncode != 0
    staged = _run(["git", "diff", "--cached", "--quiet"]).returncode != 0
    return unstaged or staged


def main() -> int:
    if not (REPO_DIR / ".git").exists():
        print("This folder is not a git repository yet.")
        print("Clone it first with:")
        print("  git clone https://github.com/maracprue/aws-download-app.git")
        return 1

    print("Checking for updates...")

    stashed = False
    if _has_local_changes():
        print()
        print("Local changes detected in this folder -- stashing them "
              "temporarily so the update can proceed...")
        result = _run(["git", "stash", "push", "-u", "-m", "update_app.py autostash"])
        if result.returncode != 0:
            print()
            print("Could not stash local changes. Resolve them manually "
                  "(git status), then re-run this script.")
            return 1
        stashed = True

    result = _run(["git", "pull", "--ff-only"])
    if result.returncode != 0:
        print()
        if stashed:
            print("Update failed even after stashing. Your local changes are "
                  "safely saved -- run \"git stash list\" and \"git stash pop\" "
                  "to restore them once resolved.")
        else:
            print("Update failed. You may have local changes that conflict "
                  "with the update. Resolve them manually, then re-run this "
                  "script.")
        return 1

    if stashed:
        print()
        print("Reapplying your local changes on top of the update...")
        result = _run(["git", "stash", "pop"])
        if result.returncode != 0:
            print()
            print("Update succeeded, but your local changes conflict with the "
                  "new code. They are safe in the stash -- run "
                  "\"git stash list\" and \"git stash pop\" to resolve the "
                  "conflict manually.")
            return 1

    print()
    print("Installing/updating Python dependencies...")
    python = next((p for p in _PYTHON_CANDIDATES if p.exists()), None)
    if python is None:
        print("Could not find a Python interpreter. Falling back to 'python' on PATH.")
        python = Path("python")

    req_file = REPO_DIR / "aws_download_app" / "requirements.txt"
    pip_result = _run([str(python), "-m", "pip", "install", "-r", str(req_file), "--upgrade"])
    if pip_result.returncode != 0:
        print()
        print("Dependency install failed -- check the output above.")
        return 1

    print()
    print("Update complete! Launch the app with launch_aws_app.bat")
    return 0


if __name__ == "__main__":
    sys.exit(main())
