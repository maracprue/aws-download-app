"""
SSO token cache inspection + proactive/on-demand session refresh.

AWS CLI writes the SSO access token to a JSON file under ~/.aws/sso/cache/
with an ``expiresAt`` timestamp. Running `aws sso login` while that token is
still valid is a no-op (AWS CLI skips the browser flow), so blindly calling
it on a fixed timer does NOT reliably renew the session. Instead we read the
real expiry from the cache and only trigger a login when we're within a
buffer window of (or past) that expiry — that's the only way to guarantee
the CLI actually performs a fresh login.
"""

from __future__ import annotations

import configparser
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

_SSO_CACHE_DIR = Path.home() / ".aws" / "sso" / "cache"
_AWS_CONFIG_PATH = Path.home() / ".aws" / "config"

# Default safety buffer: refresh if less than this many seconds remain.
DEFAULT_BUFFER_SECONDS = 10 * 60  # 10 minutes


def _parse_expires_at(value: str) -> Optional[datetime]:
    """Parse the various timestamp formats seen in the SSO token cache."""
    value = value.strip()
    fmts = (
        "%Y-%m-%dT%H:%M:%SZ",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SUTC",
    )
    for fmt in fmts:
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _get_sso_start_url(profile: Optional[str]) -> Optional[str]:
    """
    Resolve the sso_start_url used by *profile*, whether it's defined
    directly on the profile (legacy) or via an [sso-session ...] block.
    """
    if not _AWS_CONFIG_PATH.exists():
        return None

    cfg = configparser.ConfigParser()
    cfg.read(str(_AWS_CONFIG_PATH))

    section = f"profile {profile}" if profile else "default"
    if not cfg.has_section(section) and section != "default":
        return None

    if cfg.has_option(section, "sso_start_url"):
        return cfg.get(section, "sso_start_url")

    if cfg.has_option(section, "sso_session"):
        session_name = cfg.get(section, "sso_session")
        session_section = f"sso-session {session_name}"
        if cfg.has_section(session_section) and cfg.has_option(session_section, "sso_start_url"):
            return cfg.get(session_section, "sso_start_url")

    return None


def get_sso_expiry(profile: Optional[str] = None) -> Optional[datetime]:
    """
    Return the expiry timestamp (UTC) of the cached SSO token for *profile*,
    or None if it can't be determined (missing cache, unparsable, etc.).

    If multiple cache entries match (e.g. stale files from previous logins),
    the latest ``expiresAt`` is returned.
    """
    if not _SSO_CACHE_DIR.exists():
        return None

    start_url = _get_sso_start_url(profile)

    latest: Optional[datetime] = None
    for cache_file in _SSO_CACHE_DIR.glob("*.json"):
        try:
            data = json.loads(cache_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        if "expiresAt" not in data:
            continue

        # If we know the expected start URL, only consider matching entries.
        if start_url and data.get("startUrl") and data.get("startUrl") != start_url:
            continue

        expiry = _parse_expires_at(str(data["expiresAt"]))
        if expiry and (latest is None or expiry > latest):
            latest = expiry

    return latest


def seconds_until_sso_expiry(profile: Optional[str] = None) -> Optional[float]:
    """Seconds remaining until the cached SSO token expires (negative if already expired)."""
    expiry = get_sso_expiry(profile)
    if expiry is None:
        return None
    return (expiry - datetime.now(timezone.utc)).total_seconds()


def ensure_sso_valid(
    profile: Optional[str] = None,
    buffer_seconds: int = DEFAULT_BUFFER_SECONDS,
    emit: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Check the real SSO token expiry and refresh via `aws sso login` only
    if needed (expired, near-expiry, or unknown).

    Returns True if the session is valid after this call (either it already
    was, or the refresh login succeeded); False if a needed refresh failed.
    """
    from utils.aws_auth import run_sso_login  # local import avoids a cycle

    def _log(msg: str) -> None:
        if emit:
            emit(msg)

    remaining = seconds_until_sso_expiry(profile)

    if remaining is not None and remaining > buffer_seconds:
        return True  # still comfortably valid — no action needed

    if remaining is None:
        _log("Could not determine SSO token expiry — refreshing to be safe...")
    elif remaining <= 0:
        _log("AWS SSO session has expired — refreshing login...")
    else:
        _log(f"AWS SSO session expires in {int(remaining)}s — refreshing login early...")

    ok, output = run_sso_login(profile)
    if ok:
        _log("AWS SSO login refreshed successfully.")
    else:
        _log(f"AWS SSO login refresh FAILED: {output}")
    return ok


# Error codes that indicate the credentials/token are no longer valid,
# as opposed to a transient network/service error.
_AUTH_ERROR_CODES = {
    "ExpiredToken",
    "ExpiredTokenException",
    "InvalidClientTokenId",
    "UnauthorizedException",
    "AccessDenied",
    "RequestExpired",
}


def is_auth_error(exc: BaseException) -> bool:
    """True if *exc* looks like an expired/invalid-credentials error."""
    try:
        from botocore.exceptions import ClientError
    except Exception:
        return False

    if not isinstance(exc, ClientError):
        return False
    code = exc.response.get("Error", {}).get("Code", "")
    return code in _AUTH_ERROR_CODES
