"""Background upload runner — persists across Streamlit reruns.

A single UploadJob instance is stored at module level so it survives
Streamlit's script re-execution on every UI interaction.  Python daemon
threads are NOT killed when Streamlit reruns the script, so large uploads
keep running even if the user clicks somewhere accidentally.
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

_LOG_DIR = Path(__file__).resolve().parent.parent  # aws_download_app/


class UploadJob:
    """State for a running or completed upload job."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.status: str = "running"  # "running" | "done" | "failed"
        self.thread: threading.Thread | None = None
        self.error: str | None = None
        self.result: Any = None  # (uploaded_count, skipped_count) on success

    def emit(self, msg: str) -> None:
        """Append a log line — safe to call from any thread."""
        try:
            with open(self.log_path, "a", encoding="utf-8") as fh:
                fh.write(msg + "\n")
        except Exception:
            pass

    def get_log(self) -> str:
        """Return the full log file content."""
        try:
            return self.log_path.read_text(encoding="utf-8")
        except Exception:
            return "(log not available)"

    @property
    def is_running(self) -> bool:
        return self.status == "running"


# Module-level singleton — NOT reset when Streamlit reruns the script.
_current_job: UploadJob | None = None


def get_current_job() -> UploadJob | None:
    return _current_job


def clear_job() -> None:
    global _current_job
    _current_job = None


def start_upload_job(fn: Callable, **kwargs) -> UploadJob:
    """Run *fn* in a background daemon thread.

    *fn* must accept an ``emit`` keyword argument for streaming log lines.
    All other *kwargs* are forwarded unchanged.

    Returns the UploadJob immediately; the thread keeps running independently
    even if Streamlit reruns the page script due to a UI interaction.
    """
    global _current_job
    log_path = _LOG_DIR / f"upload_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    job = UploadJob(log_path)

    def _run() -> None:
        try:
            result = fn(emit=job.emit, **kwargs)
            job.result = result
            job.status = "done"
            job.emit("\n=== Upload complete ✓ ===")
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.emit(f"\n=== Upload FAILED ===\n{traceback.format_exc()}")

    job.thread = threading.Thread(target=_run, daemon=True)
    job.thread.start()
    _current_job = job
    return job
