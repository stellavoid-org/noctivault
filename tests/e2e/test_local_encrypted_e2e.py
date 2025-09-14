import secrets
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_load_from_encrypted_local_store_keyfile(tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings
    from noctivault.io.enc import seal_with_key

    # prepare key
    key = secrets.token_bytes(32)
    key_path = tmp_path / "local.key"
    key_path.write_bytes(key)

    # plaintext mocks YAML (no refs)
    yaml_text = textwrap.dedent(
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
        """
    ).encode("utf-8")

    # seal and write .enc
    enc_bytes = seal_with_key(yaml_text, key)
    (tmp_path / "noctivault.local-store.yaml.enc").write_bytes(enc_bytes)

    # write refs file
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

    # load via client
    settings = NoctivaultSettings(source="local")
    # attach local_enc-like fields dynamically until model is extended
    # For now we rely on default behavior if implemented; tests will adapt when LocalEncSettings exists.
    nv = Noctivault(settings)
    secrets_node = nv.load(local_store_path=str(tmp_path))

    assert secrets_node.password.get() == "00123"
    assert secrets_node.database.port.get() == "5432"
