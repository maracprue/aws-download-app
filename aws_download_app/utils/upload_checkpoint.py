"""
Resume support for large uploads.

If a large upload is interrupted (crash, closed terminal, killed process),
we don't want to have to start over from file 1. Each upload job writes its
list of successfully-completed S3 keys to a small JSON checkpoint file on
disk, keyed by a hash of (bucket, dest_prefix, source path). On the next
attempt with the same source/destination, those keys are automatically
skipped. The checkpoint file is deleted once the job finishes successfully.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Iterable

_CHECKPOINT_DIR = Path(__file__).resolve().parent.parent / ".upload_checkpoints"


def checkpoint_id_for(bucket: str, dest_prefix: str, source: str) -> str:
    """Stable id derived from the upload's identity (bucket + prefix + source path)."""
    raw = f"{bucket}|{dest_prefix.strip('/')}|{str(Path(source).resolve())}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _path_for(checkpoint_id: str) -> Path:
    return _CHECKPOINT_DIR / f"{checkpoint_id}.json"


def load_completed_keys(checkpoint_id: str) -> set[str]:
    """Return the set of S3 keys already uploaded in a previous, interrupted attempt."""
    path = _path_for(checkpoint_id)
    if not path.exists():
        return set()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return set(data.get("completed_keys", []))
    except Exception:
        return set()


def append_completed_keys(checkpoint_id: str, keys: Iterable[str]) -> None:
    """Merge *keys* into the on-disk checkpoint (called after each chunk completes)."""
    keys = list(keys)
    if not keys:
        return
    _CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    path = _path_for(checkpoint_id)
    existing = load_completed_keys(checkpoint_id)
    existing.update(keys)
    path.write_text(json.dumps({"completed_keys": sorted(existing)}), encoding="utf-8")


def clear_checkpoint(checkpoint_id: str) -> None:
    """Remove the checkpoint file — called once a job completes successfully."""
    try:
        _path_for(checkpoint_id).unlink(missing_ok=True)
    except Exception:
        pass
