"""AWS credential check and SSO login helpers."""

from __future__ import annotations

import subprocess
from typing import Optional


def check_credentials(profile: Optional[str] = None) -> tuple[bool, str]:
    """
    Check if AWS credentials are valid.

    Returns (True, identity_string) if valid,
            (False, error_message) if not.
    """
    try:
        import boto3
        from botocore.exceptions import ProfileNotFound, NoCredentialsError, ClientError

        profile = profile.strip() if profile else None
        try:
            session = boto3.Session(profile_name=profile)
        except ProfileNotFound:
            return False, f"AWS profile '{profile}' not found — check the profile name."

        sts = session.client("sts")
        try:
            identity = sts.get_caller_identity()
        except NoCredentialsError:
            return False, "No AWS credentials found. Log in with AWS SSO."
        except ClientError as e:
            code = e.response.get("Error", {}).get("Code", "")
            if code in ("ExpiredToken", "InvalidClientTokenId"):
                return False, "AWS session expired — log in again."
            return False, f"AWS error: {e}"

        account = identity.get("Account", "?")
        arn = identity.get("Arn", "?")
        role = arn.split("/")[-1] if "/" in arn else arn
        return True, f"Account: {account}  |  Role: {role}"

    except Exception as e:
        return False, f"Unexpected error checking credentials: {e}"


def _get_sso_session_name(profile: str) -> Optional[str]:
    """
    Look up the sso_session name for a given profile in ~/.aws/config.
    Returns None if not found.
    """
    try:
        import configparser
        from pathlib import Path

        config_path = Path.home() / ".aws" / "config"
        if not config_path.exists():
            return None
        cfg = configparser.ConfigParser()
        cfg.read(str(config_path))
        section = f"profile {profile}"
        if cfg.has_option(section, "sso_session"):
            return cfg.get(section, "sso_session")
    except Exception:
        pass
    return None


def run_sso_login(profile: Optional[str] = None) -> tuple[bool, str]:
    """
    Run `aws sso login` using --sso-session when available (avoids scope bugs
    with --profile in some AWS CLI versions), falling back to --profile.

    Returns (True, output) on success, (False, output) on failure.
    """
    profile = profile.strip() if profile else None

    # Prefer --sso-session to avoid the AWS CLI bug where --profile is
    # incorrectly used as the OAuth scope value.
    cmd = ["aws", "sso", "login"]
    if profile:
        sso_session = _get_sso_session_name(profile)
        if sso_session:
            cmd += ["--sso-session", sso_session]
        else:
            cmd += ["--profile", profile]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,  # 5-minute timeout for browser auth
        )
        output = (result.stdout + result.stderr).strip()
        return result.returncode == 0, output or "Login completed."
    except FileNotFoundError:
        return False, "AWS CLI not found — make sure it's installed and on your PATH."
    except subprocess.TimeoutExpired:
        return False, "Login timed out (5 minutes). Please try again."
    except Exception as e:
        return False, f"Error running aws sso login: {e}"
