import secrets
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_enc_precedence_over_plain_yaml(tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings
    from noctivault.io.enc import seal_with_key

    # write plain mocks yaml with different value
    (tmp_path / "noctivault.local-store.yaml").write_text(
        textwrap.dedent(
            """
            platform: google
            gcp_project_id: p
            secret-mocks:
              - name: x
                value: "plain"
                version: 1
            """
        ),
        encoding="utf-8",
    )
    # refs file
    (tmp_path / "noctivault.yaml").write_text(
        textwrap.dedent(
            """
            secret-refs:
              - platform: google
                gcp_project_id: p
                cast: password
                ref: x
                version: 1
            """
        ),
        encoding="utf-8",
    )

    # write .enc with desired value
    key = secrets.token_bytes(32)
    (tmp_path / "local.key").write_bytes(key)
    yml = textwrap.dedent(
        """
        platform: google
        gcp_project_id: p
        secret-mocks:
          - name: x
            value: "enc"
            version: 1
        """
    ).encode("utf-8")
    (tmp_path / "noctivault.local-store.yaml.enc").write_bytes(seal_with_key(yml, key))

    nv = Noctivault(NoctivaultSettings(source="local"))
    secrets_node = nv.load(local_store_path=str(tmp_path))
    assert secrets_node.password.get() == "enc"
