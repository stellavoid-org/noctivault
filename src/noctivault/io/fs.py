from __future__ import annotations

from pathlib import Path

DEFAULT_LOCAL_STORE_FILENAME = "noctivault.local-store.yaml"


def resolve_local_store_path(base: str) -> str:
    """Resolve a directory or file path to a concrete YAML file path.

    - If `base` is a directory path, returns `base/DEFAULT_LOCAL_STORE_FILENAME` if it exists.
    - If `base` is a file path, returns it if it exists.
    - Otherwise, raises FileNotFoundError.
    """
    p = Path(base)
    if p.is_dir():
        candidate = p / DEFAULT_LOCAL_STORE_FILENAME
        if candidate.exists():
            return str(candidate)
        raise FileNotFoundError(f"{candidate} not found")
    if p.is_file():
        return str(p)
    raise FileNotFoundError(f"{p} not found")
