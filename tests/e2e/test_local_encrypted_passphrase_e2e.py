import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_load_from_encrypted_local_store_passphrase(tmp_path: Path):
    from noctivault.client import LocalEncSettings, Noctivault, NoctivaultSettings
    from noctivault.io.enc import seal_with_passphrase

    yml = textwrap.dedent(
        """
        platform: google
        gcp_project_id: p
        secret-mocks:
          - name: x
            value: "00123"
            version: 1
        secret-refs:
          - platform: google
            gcp_project_id: p
            cast: password
            ref: x
            version: 1
        """
    ).encode("utf-8")

    (tmp_path / "noctivault.local-store.yaml.enc").write_bytes(seal_with_passphrase(yml, "s3cret"))

    settings = NoctivaultSettings(source="local", local_enc=LocalEncSettings(mode="passphrase"))
    nv = Noctivault(settings)
    # for tests, allow passphrase from env or settings extension; we pass via env to avoid storing in settings
    # but the client helper will look for settings first when mode == 'passphrase'. We'll extend LocalEncSettings shortly.
    # Temporarily we rely on env fallback in client.
    import os

    os.environ["NOCTIVAULT_LOCAL_PASSPHRASE"] = "s3cret"
    try:
        secrets_node = nv.load(local_store_path=str(tmp_path))
        assert secrets_node.password.get() == "00123"
    finally:
        os.environ.pop("NOCTIVAULT_LOCAL_PASSPHRASE", None)
