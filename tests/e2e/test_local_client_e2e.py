import hashlib
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def write_yaml(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "noctivault.local-store.yaml"
    p.write_text(textwrap.dedent(text), encoding="utf-8")
    return p


def test_client_load_and_get_and_display_hash(tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings

    # mocks
    write_yaml(
        tmp_path,
        """
        platform: google
        gcp_project_id: p
        secret-mocks:
          - name: x
            value: "00123"
            version: 1
          - name: port
            value: "5432"
            version: 1
        """,
    )
    # refs
    (tmp_path / "noctivault.yaml").write_text(
        textwrap.dedent(
            """
            secret-refs:
              - platform: google
                gcp_project_id: p
                cast: password
                ref: x
                version: 1
                type: str
              - key: database
                children:
                  - platform: google
                    gcp_project_id: p
                    cast: port
                    ref: port
                    version: 1
                    type: int
            """
        ),
        encoding="utf-8",
    )

    nv = Noctivault(NoctivaultSettings(source="local"))
    secrets = nv.load(local_store_path=str(tmp_path))

    # get(path) follows type
    assert nv.get("password") == "00123"
    assert nv.get("database.port") == 5432

    # display_hash over pre-cast string
    h = hashlib.sha3_256("00123".encode("utf-8")).hexdigest()
    assert nv.display_hash("password") == h

    # SecretNode equals
    assert secrets.password.equals("00123") is True
    assert secrets.database.port.equals("5432") is True


def test_client_get_missing_key_raises(tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings

    write_yaml(
        tmp_path,
        """
        platform: google
        gcp_project_id: p
        secret-mocks: []
        """,
    )
    # empty refs file
    (tmp_path / "noctivault.yaml").write_text("secret-refs: []\n", encoding="utf-8")
    nv = Noctivault(NoctivaultSettings(source="local"))
    nv.load(local_store_path=str(tmp_path))
    with pytest.raises(KeyError):
        nv.get("missing")
