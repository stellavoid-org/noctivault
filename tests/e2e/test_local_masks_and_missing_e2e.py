import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def write_yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "noctivault.local-store.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def test_masks_in_to_dict_and_repr(tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings

    write_yaml(
        tmp_path,
        """
        platform: google
        gcp_project_id: p
        secret-mocks:
          - name: pw
            value: "secret"
            version: 1
        secret-refs:
          - platform: google
            gcp_project_id: p
            cast: password
            ref: pw
            version: 1
        """,
    )
    nv = Noctivault(NoctivaultSettings(source="local"))
    secrets = nv.load(local_store_path=str(tmp_path))

    assert secrets.to_dict(reveal=False)["password"] == "***"
    assert "***" in repr(secrets)
    assert secrets.to_dict(reveal=True)["password"] == "secret"


def test_missing_local_mock_raises(tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings
    from noctivault.core.errors import MissingLocalMockError

    write_yaml(
        tmp_path,
        """
        platform: google
        gcp_project_id: p
        secret-mocks: []
        secret-refs:
          - platform: google
            gcp_project_id: p
            cast: sample
            ref: missing
            version: 1
        """,
    )
    nv = Noctivault(NoctivaultSettings(source="local"))
    with pytest.raises(MissingLocalMockError):
        nv.load(local_store_path=str(tmp_path))
