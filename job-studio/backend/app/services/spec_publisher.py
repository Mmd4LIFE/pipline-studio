from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from app.config import get_settings


def managed_root() -> Path:
    return Path(get_settings().managed_jobs_dir)


def atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    data = json.dumps(payload, indent=2, sort_keys=True)
    with tmp.open("w", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(tmp, path)
    directory = os.open(str(path.parent), os.O_RDONLY)
    try:
        os.fsync(directory)
    finally:
        os.close(directory)


def publish_spec(spec: dict[str, Any]) -> None:
    job_id = spec["job_id"]
    revision = spec["revision"]
    root = managed_root()
    revision_path = root / "revisions" / job_id / f"{revision}.json"
    current_path = root / "current" / f"{job_id}.json"
    atomic_write(revision_path, spec)
    atomic_write(current_path, spec)


def unpublish_spec(job_id: str) -> None:
    current_path = managed_root() / "current" / f"{job_id}.json"
    if current_path.exists():
        current_path.unlink()
