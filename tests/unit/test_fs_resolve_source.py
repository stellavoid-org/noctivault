from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_resolve_source_prefers_enc(tmp_path: Path):
    from noctivault.io.fs import (
        DEFAULT_LOCAL_STORE_ENC_FILENAME,
        DEFAULT_LOCAL_STORE_FILENAME,
        resolve_local_store_source,
    )

    (tmp_path / DEFAULT_LOCAL_STORE_FILENAME).write_text("platform: google\ngcp_project_id: p\n")
    (tmp_path / DEFAULT_LOCAL_STORE_ENC_FILENAME).write_bytes(b"NVLE1\x00" * 4)

    kind, path = resolve_local_store_source(str(tmp_path))
    assert kind == "enc"
    assert path.endswith(DEFAULT_LOCAL_STORE_ENC_FILENAME)


def test_resolve_source_file_kinds(tmp_path: Path):
    from noctivault.io.fs import (
        DEFAULT_LOCAL_STORE_ENC_FILENAME,
        DEFAULT_LOCAL_STORE_FILENAME,
        resolve_local_store_source,
    )

    enc = tmp_path / DEFAULT_LOCAL_STORE_ENC_FILENAME
    enc.write_bytes(b"NVLE1\x00" * 4)
    kind, path = resolve_local_store_source(str(enc))
    assert kind == "enc" and path == str(enc)

    yml = tmp_path / DEFAULT_LOCAL_STORE_FILENAME
    yml.write_text("platform: google\ngcp_project_id: p\n")
    kind2, path2 = resolve_local_store_source(str(yml))
    assert kind2 == "yaml" and path2 == str(yml)


def test_resolve_source_missing_raises(tmp_path: Path):
    from noctivault.io.fs import resolve_local_store_source

    with pytest.raises(FileNotFoundError):
        resolve_local_store_source(str(tmp_path))
