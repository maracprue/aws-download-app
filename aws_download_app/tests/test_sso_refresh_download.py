"""
Live integration test for the SSO session-refresh flow (see utils/session_guard.py).

WHAT THIS DOES
--------------
1. Confirms your AWS SSO credentials currently work.
2. Backs up your real SSO token cache file, then edits its `expiresAt` to a
   few minutes in the future — this makes our code (and the real `aws sso
   login` command) treat the session as "about to expire", without touching
   your actual IdP/browser session.
3. Downloads a batch of small real files from S3 (from a scratch `test/`
   prefix in the bucket) with an artificial delay between files, so the
   simulated expiry is crossed *while the batch is running*.
4. Watches for our code to pause, run a real `aws sso login`, and resume
   the same batch — proving the pause → relogin → resume flow works
   end-to-end against real AWS infrastructure.
5. Cleans up: removes downloaded test files and restores the original SSO
   cache if a fresh login never actually happened (e.g. on failure).

This is a manual/interactive test — it performs a REAL `aws sso login` and
REAL S3 downloads. Run it directly, don't wire it into CI:

    python tests\test_sso_refresh_download.py
"""

from __future__ import annotations

import json
import shutil
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from download.s3_download import download_prefix, list_all_objects  # noqa: E402
from utils.aws_auth import check_credentials  # noqa: E402
from utils.config import AWS_PROFILE, S3_BUCKET  # noqa: E402
from utils.session_guard import _sso_cache_file_for  # noqa: E402

PROFILE = AWS_PROFILE or None
TEST_PREFIX = "test/824647/Metadata/Processing Scripts/"
MAX_FILE_SIZE = 50_000       # skip the couple of large .mat files in this prefix
SIMULATED_EXPIRY_SECONDS = 40    # simulate "expires in 40 seconds"
REFRESH_BUFFER_SECONDS = 20      # only refresh once within 20s of that expiry
DELAY_BETWEEN_FILES = 15         # seconds — paces the batch so expiry is crossed mid-run
MAX_FILES = 5                    # keep the test batch small and bounded

START = time.monotonic()


def log(msg: str) -> None:
    print(f"[t+{time.monotonic() - START:6.1f}s] {msg}")


def find_cache_file(profile: str | None) -> Path | None:
    """Find the exact SSO cache file AWS CLI uses for *profile*."""
    return _sso_cache_file_for(profile)


def main() -> int:
    log(f"Profile={PROFILE!r}  Bucket={S3_BUCKET!r}  Prefix={TEST_PREFIX!r}")

    ok, msg = check_credentials(PROFILE)
    log(f"Initial credential check: {ok} ({msg})")
    if not ok:
        log("Credentials aren't valid — log in normally first, then re-run this test.")
        return 1

    cache_file = find_cache_file(PROFILE)
    if not cache_file:
        log("Could not locate the SSO token cache file — aborting.")
        return 1
    log(f"Using SSO cache file: {cache_file}")

    original_content = cache_file.read_text(encoding="utf-8")
    original_data = json.loads(original_content)

    simulated_expiry = datetime.now(timezone.utc) + timedelta(seconds=SIMULATED_EXPIRY_SECONDS)
    tampered_data = dict(original_data)
    tampered_data["expiresAt"] = simulated_expiry.strftime("%Y-%m-%dT%H:%M:%SUTC")
    # Also strip the refresh token: botocore's SSOTokenProvider will silently
    # (and invisibly) use a valid refreshToken to renew the access token the
    # instant it sees a near/at-expiry token — no browser, no `aws sso
    # login` call, nothing for our code to observe. Removing it forces a
    # REAL auth failure so we can actually exercise our relogin path instead
    # of watching botocore quietly heal itself first.
    tampered_data.pop("refreshToken", None)
    cache_file.write_text(json.dumps(tampered_data), encoding="utf-8")
    log(f"Simulated token expiry set to {SIMULATED_EXPIRY_SECONDS}s from now "
        f"({tampered_data['expiresAt']}), refresh token removed to force a real relogin.")

    # List the small files we'll download (filter applied again inside
    # download_prefix, but we log the plan here too).
    objects = list_all_objects(S3_BUCKET, TEST_PREFIX, PROFILE)
    small = [(k, s) for k, s in objects if s <= MAX_FILE_SIZE]
    log(f"Found {len(small)} small file(s) under the test prefix "
        f"(of {len(objects)} total) — using first 10.")
    plan_count = min(10, len(small))
    if plan_count == 0:
        log("No small files found to test with — aborting.")
        cache_file.write_text(original_content, encoding="utf-8")
        return 1

    local_dest = Path(__file__).resolve().parent / "_scratch_download"
    if local_dest.exists():
        shutil.rmtree(local_dest)
    local_dest.mkdir(parents=True)

    relogin_detected = False

    def emit(line: str) -> None:
        nonlocal relogin_detected
        if "refreshing login" in line.lower() or "sso login" in line.lower():
            relogin_detected = True
        log(line)

    try:
        # max_files bounds this to a small, quick batch; max_file_size_bytes
        # excludes the couple of large .mat files that live in this prefix.
        downloaded, skipped = download_prefix(
            bucket=S3_BUCKET,
            prefix=TEST_PREFIX,
            local_dest=local_dest,
            profile=PROFILE,
            skip_existing=False,
            emit=emit,
            buffer_seconds=REFRESH_BUFFER_SECONDS,
            delay_between_files=DELAY_BETWEEN_FILES,
            max_file_size_bytes=MAX_FILE_SIZE,
            max_files=MAX_FILES,
        )
        log(f"Download finished: {downloaded} downloaded, {skipped} skipped.")
    except Exception as exc:
        log(f"Download FAILED: {exc}")
        raise
    finally:
        # If our tampered expiresAt is still sitting in the cache, no real
        # login ever ran (or it failed) — restore the original valid token
        # so we don't leave the profile in a bad state.
        current = json.loads(cache_file.read_text(encoding="utf-8"))
        if current.get("expiresAt") == tampered_data["expiresAt"]:
            log("No fresh login was detected in the cache — restoring original token.")
            cache_file.write_text(original_content, encoding="utf-8")
        else:
            log("Cache now holds a freshly-issued token from the real `aws sso login` — leaving it.")

        downloaded_files = list(local_dest.rglob("*"))
        file_count = sum(1 for p in downloaded_files if p.is_file())
        log(f"Cleaning up {file_count} downloaded test file(s) at {local_dest}")
        shutil.rmtree(local_dest, ignore_errors=True)

    if relogin_detected:
        log("RESULT: [OK] pause -> aws sso login -> resume was observed during the batch.")
    else:
        log("RESULT: [WARN] no relogin was triggered — batch may have finished before "
            "the simulated expiry was reached. Try increasing DELAY_BETWEEN_FILES.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
