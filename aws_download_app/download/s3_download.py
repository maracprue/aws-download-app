"""
S3 folder download helper.

Downloads all objects under an S3 prefix to a local directory,
preserving the relative key structure.
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Callable, Optional

from download.s3_browser import _make_s3_client
from utils.session_guard import DEFAULT_BUFFER_SECONDS, ensure_sso_valid, is_auth_error


def list_all_objects(
    bucket: str,
    prefix: str,
    profile: Optional[str] = None,
) -> list[tuple[str, int]]:
    """
    Return a list of (key, size_bytes) for every object under *prefix*.
    """
    s3 = _make_s3_client(profile)
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    paginator = s3.get_paginator("list_objects_v2")
    results: list[tuple[str, int]] = []
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            if key.endswith("/"):  # skip directory placeholders
                continue
            results.append((key, obj.get("Size", 0)))
    return results


def download_prefix(
    bucket: str,
    prefix: str,
    local_dest: Path,
    profile: Optional[str] = None,
    progress_callback: Callable[[int, int, str], None] | None = None,
    skip_existing: bool = False,
    emit: Callable[[str], None] | None = None,
    buffer_seconds: int = DEFAULT_BUFFER_SECONDS,
    delay_between_files: float = 0.0,
    max_file_size_bytes: Optional[int] = None,
    max_files: Optional[int] = None,
) -> tuple[int, int]:
    """
    Download all objects under *prefix* from *bucket* to *local_dest*.

    The S3 prefix itself is stripped, so keys are recreated relative to local_dest.

    Args:
        bucket:              S3 bucket name.
        prefix:              S3 prefix (folder) to download.
        local_dest:          Local directory to write files into.
        profile:             Optional AWS profile name.
        progress_callback:   Called as callback(current_index, total, key) for each file.
        skip_existing:       If True, skip files that already exist locally.
        emit:                Optional callable for logging each action line.
        buffer_seconds:      How far ahead of real SSO token expiry to refresh
                             (see utils.session_guard.ensure_sso_valid). Exposed
                             mainly for testing the refresh flow with a short window.
        delay_between_files: Artificial pause (seconds) before each file — for
                             testing the pause/refresh/resume flow in real time.
                             Defaults to 0 (no effect on normal use).
        max_file_size_bytes: If set, objects larger than this are skipped —
                             mainly useful for testing against a real prefix
                             while excluding large files.
        max_files:           If set, only the first N objects under the prefix
                             are considered — mainly useful for bounding a test run.

    Returns:
        Tuple of (downloaded_count, skipped_count).
    """
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    objects = list_all_objects(bucket, prefix, profile)
    if max_file_size_bytes is not None:
        objects = [(k, s) for k, s in objects if s <= max_file_size_bytes]
    if max_files is not None:
        objects = objects[:max_files]
    total = len(objects)
    if total == 0:
        if emit:
            emit(f"No objects found under s3://{bucket}/{prefix}")
        return 0, 0

    local_dest = Path(local_dest)
    local_dest.mkdir(parents=True, exist_ok=True)

    downloaded = 0
    skipped = 0

    # Build the S3 client ONCE (see the matching comment in upload_files —
    # rebuilding per file leaks connection pools / transfer threads across
    # thousands of files and can destabilize the machine).
    s3 = _make_s3_client(profile)

    for i, (key, size) in enumerate(objects, 1):
        if max_file_size_bytes is not None and size > max_file_size_bytes:
            skipped += 1
            if emit:
                emit(f"  [SKIP too large] {key} ({size} bytes)")
            if progress_callback:
                progress_callback(i, total, key)
            continue

        # Strip the prefix to get the relative path
        relative = key[len(prefix):]
        local_path = local_dest / Path(relative)
        local_path.parent.mkdir(parents=True, exist_ok=True)

        if skip_existing and local_path.exists():
            skipped += 1
            if emit:
                emit(f"  [SKIP]     {key}")
            if progress_callback:
                progress_callback(i, total, key)
            continue

        if delay_between_files:
            if emit:
                emit(f"  (test pacing: sleeping {delay_between_files}s before next file)")
            time.sleep(delay_between_files)

        if progress_callback:
            progress_callback(i, total, key)

        if emit:
            emit(f"  [DOWNLOAD] {key}")

        # Proactively refresh the SSO session if it's near/at real expiry
        # before starting the next file (cheap: reads a local cache file).
        valid, refreshed = ensure_sso_valid(profile, buffer_seconds=buffer_seconds, emit=emit)
        if not valid:
            raise RuntimeError("AWS SSO session refresh failed mid-download.")
        if refreshed:
            s3 = _make_s3_client(profile)

        try:
            s3.download_file(bucket, key, str(local_path))
        except Exception as exc:
            if not is_auth_error(exc):
                raise
            # Token expired mid-transfer (e.g. a very large file). The
            # partially-written file is incomplete/corrupt — remove it so a
            # retry (here, or a future skip_existing run) doesn't mistake it
            # for a completed download.
            if emit:
                emit(f"  Auth error mid-download ({exc}) — refreshing session and retrying...")
            local_path.unlink(missing_ok=True)
            valid, _ = ensure_sso_valid(profile, buffer_seconds=10**9, emit=emit)
            if not valid:
                raise
            s3 = _make_s3_client(profile)
            s3.download_file(bucket, key, str(local_path))

        downloaded += 1

    return downloaded, skipped
