"""Background download runner — persists across Streamlit reruns.

Mirrors upload_runner.py: a single DownloadJob instance is stored at module
level so it survives Streamlit's script re-execution on every UI interaction.
Python daemon threads are NOT killed when Streamlit reruns the script, so
large downloads keep running even if the user clicks somewhere accidentally.
"""

from __future__ import annotations

import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Any

_LOG_DIR = Path(__file__).resolve().parent.parent  # aws_download_app/


class DownloadJob:
    """State for a running or completed download job."""

    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.status: str = "running"  # "running" | "done" | "failed"
        self.thread: threading.Thread | None = None
        self.error: str | None = None
        self.result: Any = None  # (downloaded_count, skipped_count) on success

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
_current_job: DownloadJob | None = None


def get_current_download_job() -> DownloadJob | None:
    return _current_job


def clear_download_job() -> None:
    global _current_job
    _current_job = None


def run_download_task(
    bucket: str,
    prefixes: list[tuple[str, str]],
    skip_existing: bool,
    profile: str | None,
    emit,
) -> tuple[int, int]:
    """
    Download one or more S3 prefixes.

    Args:
        bucket:        S3 bucket name.
        prefixes:      List of (s3_prefix, local_dest_str) pairs.
        skip_existing: Skip files already present locally.
        profile:       Optional AWS profile name.
        emit:          Log-line callback provided by the runner.

    Returns:
        (total_downloaded, total_skipped)
    """
    from download.s3_download import download_prefix

    emit(f"=== Download started {datetime.now().isoformat()} ===")
    emit(f"Bucket: {bucket}  |  Skip existing: {skip_existing}")

    total_dl = 0
    total_sk = 0

    for s3_prefix, local_dest_str in prefixes:
        emit(f"\n--- {s3_prefix} → {local_dest_str} ---")
        dl, sk = download_prefix(
            bucket=bucket,
            prefix=s3_prefix,
            local_dest=Path(local_dest_str),
            profile=profile,
            skip_existing=skip_existing,
            emit=emit,
        )
        total_dl += dl
        total_sk += sk
        emit(f"  Subtotal: {dl} downloaded, {sk} skipped")

    emit(f"\n=== Download complete — {total_dl} downloaded, {total_sk} skipped ===")
    return total_dl, total_sk


def start_download_job(
    bucket: str,
    prefixes: list[tuple[str, str]],
    skip_existing: bool,
    profile: str | None,
) -> DownloadJob:
    """
    Start a background daemon thread that downloads all requested prefixes.

    Returns the DownloadJob immediately; the thread keeps running independently
    even if Streamlit reruns the page script due to a UI interaction.
    """
    global _current_job
    log_path = _LOG_DIR / f"download_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    job = DownloadJob(log_path)

    def _run() -> None:
        try:
            result = run_download_task(
                bucket=bucket,
                prefixes=prefixes,
                skip_existing=skip_existing,
                profile=profile,
                emit=job.emit,
            )
            job.result = result
            job.status = "done"
        except Exception as exc:
            job.status = "failed"
            job.error = str(exc)
            job.emit(f"\n=== Download FAILED ===\n{traceback.format_exc()}")

    job.thread = threading.Thread(target=_run, daemon=True)
    job.thread.start()
    _current_job = job
    return job
