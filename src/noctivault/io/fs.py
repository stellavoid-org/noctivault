from __future__ import annotations

from pathlib import Path

DEFAULT_LOCAL_STORE_FILENAME = "noctivault.local-store.yaml"
DEFAULT_REFERENCE_FILENAME = "noctivault.yaml"
DEFAULT_LOCAL_STORE_ENC_FILENAME = "noctivault.local-store.yaml.enc"


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


def resolve_local_store_source(base: str) -> tuple[str, str]:
    """Resolve to either an encrypted or plaintext local store file.

    Returns a tuple (kind, path), where kind is "enc" or "yaml".
    Preference order when `base` is a directory: `.yaml.enc` first, then `.yaml`.
    """
    p = Path(base)
    if p.is_dir():
        enc = p / DEFAULT_LOCAL_STORE_ENC_FILENAME
        if enc.exists():
            return ("enc", str(enc))
        plain = p / DEFAULT_LOCAL_STORE_FILENAME
        if plain.exists():
            return ("yaml", str(plain))
        raise FileNotFoundError(f"{enc} or {plain} not found")
    if p.is_file():
        if p.name == DEFAULT_LOCAL_STORE_ENC_FILENAME:
            return ("enc", str(p))
        if p.name == DEFAULT_LOCAL_STORE_FILENAME:
            return ("yaml", str(p))
        raise FileNotFoundError(f"Unsupported file name: {p.name}")
    raise FileNotFoundError(f"{p} not found")


def resolve_reference_path(base: str) -> str:
    """Resolve to the reference file path (plaintext only).

    - If `base` is a directory, returns `<dir>/noctivault.yaml` if it exists.
    - If `base` is a file, returns it if it exists.
    - Otherwise, raises FileNotFoundError.
    """
    p = Path(base)
    if p.is_dir():
        candidate = p / DEFAULT_REFERENCE_FILENAME
        if candidate.exists():
            return str(candidate)
        raise FileNotFoundError(f"{candidate} not found")
    if p.is_file():
        return str(p)
    raise FileNotFoundError(f"{p} not found")
