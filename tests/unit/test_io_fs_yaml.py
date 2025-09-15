import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit


def test_path_resolver_dir_joins_default_filename(tmp_path: Path):
    from noctivault.io.fs import DEFAULT_LOCAL_STORE_FILENAME, resolve_local_store_path

    # create directory with default file
    cfg_path = tmp_path / DEFAULT_LOCAL_STORE_FILENAME
    cfg_path.write_text("platform: google\ngcp_project_id: p\n")

    resolved = resolve_local_store_path(str(tmp_path))
    assert Path(resolved) == cfg_path


def test_path_resolver_file_passthrough(tmp_path: Path):
    from noctivault.io.fs import resolve_local_store_path

    cfg_path = tmp_path / "noctivault.local-store.yaml"
    cfg_path.write_text("platform: google\ngcp_project_id: p\n")

    resolved = resolve_local_store_path(str(cfg_path))
    assert Path(resolved) == cfg_path


def test_path_resolver_missing_raises(tmp_path: Path):
    from noctivault.io.fs import resolve_local_store_path

    with pytest.raises(FileNotFoundError):
        resolve_local_store_path(str(tmp_path))  # no file inside


def test_yaml_reader_loads_utf8(tmp_path: Path):
    from noctivault.io.yaml import read_yaml

    p = tmp_path / "noctivault.local-store.yaml"
    content = textwrap.dedent(
        """
        platform: google
        gcp_project_id: p
        secret-mocks: []
        """
    )
    p.write_text(content, encoding="utf-8")

    data = read_yaml(str(p))
    assert data["platform"] == "google"
    assert data["gcp_project_id"] == "p"
