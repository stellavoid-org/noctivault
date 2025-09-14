from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def read_yaml(path: str) -> dict[str, Any]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    return data or {}
