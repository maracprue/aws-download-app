"""
S3 folder browser helpers.

Uses list_objects_v2 with Delimiter="/" to present an S3 bucket
as a navigable folder hierarchy.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class S3Object:
    key: str
    size: int  # bytes

    @property
    def name(self) -> str:
        return self.key.split("/")[-1]

    @property
    def size_human(self) -> str:
        if self.size >= 1e9:
            return f"{self.size / 1e9:.2f} GB"
        if self.size >= 1e6:
            return f"{self.size / 1e6:.1f} MB"
        if self.size >= 1e3:
            return f"{self.size / 1e3:.1f} KB"
        return f"{self.size} B"


def _make_s3_client(profile: Optional[str] = None):
    import boto3

    profile = profile.strip() if profile else None
    if not profile:
        profile = os.environ.get("AWS_PROFILE", "").strip() or None
    session = boto3.Session(profile_name=profile)
    return session.client("s3")


def list_prefix(
    bucket: str,
    prefix: str = "",
    profile: Optional[str] = None,
) -> tuple[list[str], list[S3Object]]:
    """
    List the immediate contents of *prefix* inside *bucket*.

    Returns:
        folders  — list of sub-prefix strings (each ends with "/")
        objects  — list of S3Object (files directly at this level)
    """
    s3 = _make_s3_client(profile)

    # Ensure prefix ends with "/" if non-empty
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    paginator = s3.get_paginator("list_objects_v2")
    folders: list[str] = []
    objects: list[S3Object] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes") or []:
            folders.append(cp["Prefix"])
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            # Skip the prefix placeholder itself
            if key == prefix:
                continue
            objects.append(S3Object(key=key, size=obj.get("Size", 0)))

    folders.sort()
    objects.sort(key=lambda o: o.key)
    return folders, objects


def prefix_to_breadcrumbs(prefix: str) -> list[tuple[str, str]]:
    """
    Convert an S3 prefix into a list of (label, prefix) breadcrumb tuples.

    Example: "Production/batch1/sub/" →
        [("Home", ""), ("Production", "Production/"), ("batch1", "Production/batch1/"), ...]
    """
    crumbs: list[tuple[str, str]] = [("🏠 Home", "")]
    parts = [p for p in prefix.rstrip("/").split("/") if p]
    for i, part in enumerate(parts):
        crumb_prefix = "/".join(parts[: i + 1]) + "/"
        crumbs.append((part, crumb_prefix))
    return crumbs


def folder_name(prefix: str) -> str:
    """Return the display name of a prefix (last non-empty segment)."""
    return prefix.rstrip("/").split("/")[-1] if prefix else "/"
