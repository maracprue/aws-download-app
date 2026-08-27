"""
S3 upload helpers.

Supports uploading a single file or an entire folder tree to an S3 bucket,
with optional conflict detection and skip/overwrite control.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Callable, Optional

from download.s3_browser import _make_s3_client
from utils.session_guard import ensure_sso_valid, is_auth_error


def collect_local_files(source: Path) -> list[tuple[Path, str]]:
    """
    Return a list of (local_path, relative_key) pairs for upload.

    For a single file:  [(file, file.name)]
    For a directory:    [(file, folder_name/relative/path/to/file)] — preserving
                        sub-structure under the source folder name itself.
    """
    source = Path(source)
    if source.is_file():
        return [(source, source.name)]

    items: list[tuple[Path, str]] = []
    for root, _dirs, files in os.walk(source):
        for fname in files:
            full = Path(root) / fname
            rel = Path(source.name) / full.relative_to(source)
            items.append((full, rel.as_posix()))
    items.sort(key=lambda t: t[1])
    return items


def check_existing_keys(
    bucket: str,
    keys: list[str],
    profile: Optional[str] = None,
) -> set[str]:
    """
    Return the subset of *keys* that already exist in *bucket*.

    Uses list_objects_v2 grouped by common prefixes to minimise API calls,
    then filters the response against the requested key set.
    """
    if not keys:
        return set()

    s3 = _make_s3_client(profile)
    existing: set[str] = set()
    key_set = set(keys)

    # Find the longest common prefix to narrow the listing.
    # Fall back to listing everything if there's no common prefix.
    if len(keys) == 1:
        common_prefix = "/".join(keys[0].split("/")[:-1])
        common_prefix = common_prefix + "/" if common_prefix else ""
    else:
        parts = [k.split("/") for k in keys]
        common: list[str] = []
        for segments in zip(*parts):
            if len(set(segments)) == 1:
                common.append(segments[0])
            else:
                break
        common_prefix = "/".join(common) + "/" if common else ""

    paginator = s3.get_paginator("list_objects_v2")
    for page in paginator.paginate(Bucket=bucket, Prefix=common_prefix):
        for obj in page.get("Contents") or []:
            if obj["Key"] in key_set:
                existing.add(obj["Key"])

    return existing


def upload_files(
    bucket: str,
    items: list[tuple[Path, str]],
    dest_prefix: str,
    profile: Optional[str] = None,
    overwrite: bool = True,
    emit: Callable[[str], None] | None = None,
) -> tuple[int, int]:
    """
    Upload local files to S3.

    Args:
        bucket:      Target S3 bucket.
        items:       List of (local_path, relative_key) from collect_local_files().
        dest_prefix: S3 prefix to upload under (may be empty for bucket root).
        profile:     Optional AWS profile name.
        overwrite:   If False, skip keys that already exist in S3.
        emit:        Optional callback for streaming log lines.

    Returns:
        (uploaded_count, skipped_count)
    """
    def _log(msg: str) -> None:
        if emit:
            emit(msg)

    prefix = dest_prefix.strip("/")

    # Build full S3 keys
    keyed: list[tuple[Path, str]] = []
    for local_path, rel_key in items:
        full_key = f"{prefix}/{rel_key}" if prefix else rel_key
        keyed.append((local_path, full_key))

    # Resolve conflicts up-front if skipping
    if not overwrite:
        all_keys = [k for _, k in keyed]
        _log("Checking for existing files in S3...")
        existing = check_existing_keys(bucket, all_keys, profile)
        _log(f"Found {len(existing)} existing file(s) — will skip.")
    else:
        existing = set()

    total = len(keyed)
    uploaded = 0
    skipped = 0

    # Build the S3 client ONCE. Rebuilding it per file (as an earlier version
    # did) creates a brand-new connection pool + transfer thread pool per
    # file — with thousands of files that leaks memory/sockets/threads fast
    # enough to destabilize the machine. We only rebuild when a real SSO
    # login actually ran (see ensure_sso_valid's `refreshed` flag).
    s3 = _make_s3_client(profile)

    for i, (local_path, s3_key) in enumerate(keyed, 1):
        if s3_key in existing:
            _log(f"[{i}/{total}] SKIP  {s3_key}")
            skipped += 1
            continue

        # Proactively refresh the SSO session if it's near/at real expiry
        # before starting the next file (cheap: reads a local cache file).
        valid, refreshed = ensure_sso_valid(profile, emit=emit)
        if not valid:
            _log(f"[{i}/{total}] Could not refresh AWS session — stopping upload.")
            raise RuntimeError("AWS SSO session refresh failed mid-upload.")
        if refreshed:
            s3 = _make_s3_client(profile)

        _log(f"[{i}/{total}] Uploading  {local_path.name}  →  s3://{bucket}/{s3_key}")
        try:
            s3.upload_file(str(local_path), bucket, s3_key)
        except Exception as exc:
            if not is_auth_error(exc):
                raise
            # Token expired mid-transfer (e.g. a very large file) — force a
            # fresh login, rebuild the client, and retry this file once.
            _log(f"[{i}/{total}] Auth error mid-upload ({exc}) — refreshing session and retrying...")
            valid, _ = ensure_sso_valid(profile, buffer_seconds=10**9, emit=emit)
            if not valid:
                raise
            s3 = _make_s3_client(profile)
            s3.upload_file(str(local_path), bucket, s3_key)
        uploaded += 1

    _log(f"\nDone — {uploaded} uploaded, {skipped} skipped.")
    return uploaded, skipped
