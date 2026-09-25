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
    max_items: Optional[int] = None,
) -> tuple[list[str], list[S3Object], bool]:
    """
    List the immediate contents of *prefix* inside *bucket*.

    Args:
        max_items: If set, stop fetching once folders+objects reaches this
            count. Without a cap, a prefix with an enormous number of
            immediate sub-folders/files (e.g. a bucket root used as a flat
            dumping ground for hundreds of thousands of dataset folders)
            can take a very long time to fully page through and freeze the
            UI, even though S3 itself returns each page quickly. Use
            search_prefixes() to jump straight to a known folder instead of
            listing everything.

    Returns:
        folders    — list of sub-prefix strings (each ends with "/")
        objects    — list of S3Object (files directly at this level)
        truncated  — True if max_items was hit before the listing finished
    """
    s3 = _make_s3_client(profile)

    # Ensure prefix ends with "/" if non-empty
    if prefix and not prefix.endswith("/"):
        prefix = prefix + "/"

    paginator = s3.get_paginator("list_objects_v2")
    folders: list[str] = []
    objects: list[S3Object] = []
    truncated = False

    for page in paginator.paginate(Bucket=bucket, Prefix=prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes") or []:
            folders.append(cp["Prefix"])
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            # Skip the prefix placeholder itself
            if key == prefix:
                continue
            objects.append(S3Object(key=key, size=obj.get("Size", 0)))
        if max_items is not None and len(folders) + len(objects) >= max_items:
            truncated = True
            break

    folders.sort()
    objects.sort(key=lambda o: o.key)
    return folders, objects, truncated



def search_prefixes(
    bucket: str,
    base_prefix: str,
    query: str,
    profile: Optional[str] = None,
    max_matches: int = 500,
) -> tuple[list[str], list[S3Object]]:
    """
    Find sub-folders/files directly under *base_prefix* whose name starts
    with *query* (case-sensitive, matching S3 key semantics).

    Unlike listing the entire contents of *base_prefix* and filtering
    client-side, this uses *query* as part of the S3 Prefix itself
    (Prefix = base_prefix + query). S3 keys are stored in sorted order, so
    a Prefix lookup is efficient no matter how many thousands of
    sibling folders exist at that level — it does not require paginating
    through everything else first. This is what makes searching usable in
    buckets/folders too large to browse by listing alone.

    Returns:
        folders  — matching sub-prefixes (each ends with "/")
        objects  — matching files directly at this level

    Stops early once *max_matches* combined folders+objects are found, to
    keep pathologically broad queries (e.g. a single common letter) from
    scanning unbounded results.
    """
    s3 = _make_s3_client(profile)

    if base_prefix and not base_prefix.endswith("/"):
        base_prefix = base_prefix + "/"
    query = query.strip().lstrip("/")

    search_prefix = f"{base_prefix}{query}"

    paginator = s3.get_paginator("list_objects_v2")
    folders: list[str] = []
    objects: list[S3Object] = []

    for page in paginator.paginate(Bucket=bucket, Prefix=search_prefix, Delimiter="/"):
        for cp in page.get("CommonPrefixes") or []:
            folders.append(cp["Prefix"])
        for obj in page.get("Contents") or []:
            key = obj["Key"]
            if key == search_prefix:
                continue
            objects.append(S3Object(key=key, size=obj.get("Size", 0)))
        if len(folders) + len(objects) >= max_matches:
            break

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
