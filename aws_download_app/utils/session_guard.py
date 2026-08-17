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
import hashlib
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


def _get_sso_cache_key(profile: Optional[str]) -> Optional[str]:
    """
    Return the exact string AWS CLI/botocore hashes to name the cache file
    for *profile* — the sso_session name if the profile uses the modern
    [sso-session ...] block, otherwise the legacy sso_start_url.

    Using this (rather than scanning every cache file and guessing which
    one applies) is what guarantees we read the expiry of the token this
    profile actually uses, instead of an unrelated cache entry for a
    different profile/session that happens to have a later expiry.
    """
    if not _AWS_CONFIG_PATH.exists():
        return None

    cfg = configparser.ConfigParser()
    cfg.read(str(_AWS_CONFIG_PATH))

    section = f"profile {profile}" if profile else "default"
    if not cfg.has_section(section) and section != "default":
        return None

    if cfg.has_option(section, "sso_session"):
        return cfg.get(section, "sso_session")

    if cfg.has_option(section, "sso_start_url"):
        return cfg.get(section, "sso_start_url")

    return None


def _sso_cache_file_for(profile: Optional[str]) -> Optional[Path]:
    """Return the exact cache file path AWS CLI uses for *profile*, if any."""
    cache_key = _get_sso_cache_key(profile)
    if not cache_key:
        return None
    filename = hashlib.sha1(cache_key.encode("utf-8")).hexdigest() + ".json"
    path = _SSO_CACHE_DIR / filename
    return path if path.exists() else None


def get_sso_expiry(profile: Optional[str] = None) -> Optional[datetime]:
    """
    Return the expiry timestamp (UTC) of the cached SSO token for *profile*,
    or None if it can't be determined (missing cache, unparsable, etc.).

    Reads the exact cache file AWS CLI uses for this profile (see
    _sso_cache_file_for) rather than scanning all cache files, since
    unrelated cache entries (other profiles/sessions) can have very
    different — and misleadingly later — expiry times.
    """
    cache_file = _sso_cache_file_for(profile)
    if cache_file is None:
        return None

    try:
        data = json.loads(cache_file.read_text(encoding="utf-8"))
    except Exception:
        return None

    if "expiresAt" not in data:
        return None

    return _parse_expires_at(str(data["expiresAt"]))


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
        from botocore.exceptions import (
            ClientError,
            NoAuthTokenError,
            SSOTokenLoadError,
            TokenRetrievalError,
            UnauthorizedSSOTokenError,
        )
    except Exception:
        return False

    # SSO token failures (e.g. "Token has expired and refresh failed") raise
    # botocore's own SSO/token error types, NOT ClientError — this is the
    # error boto3 actually raises when the cached SSO token is expired and
    # can't be silently refreshed, so it must be treated as an auth error too.
    if isinstance(exc, (TokenRetrievalError, SSOTokenLoadError, UnauthorizedSSOTokenError, NoAuthTokenError)):
        return True

    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        return code in _AUTH_ERROR_CODES

    return False
