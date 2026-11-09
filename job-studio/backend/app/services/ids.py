from __future__ import annotations

import hashlib
import json
import re
import secrets
import unicodedata
from typing import Any


def new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_hex(8)}"


def slugify(name: str) -> str:
    value = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    value = re.sub(r"[^a-zA-Z0-9]+", "_", value).strip("_").lower()
    value = re.sub(r"_+", "_", value)
    if not value:
        value = "job"
    return value[:80]


def spec_hash(config: dict[str, Any]) -> str:
    encoded = json.dumps(config, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
