import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_cli_seal_verify_unseal_with_passphrase(tmp_path: Path, capsys: pytest.CaptureFixture[str]):
    from noctivault.cli import main

    # prepare plaintext yaml
    plain = tmp_path / "noctivault.local-store.yaml"
    plain.write_text(
        textwrap.dedent(
            """
            platform: google
            gcp_project_id: p
            secret-mocks:
              - name: x
                value: "s"
                version: 1
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

    # seal with passphrase
    rc = main(["local", "seal", str(tmp_path), "--passphrase", "pw"])  # no key file
    assert rc == 0

    enc = tmp_path / "noctivault.local-store.yaml.enc"
    assert enc.exists()

    # verify
    rc = main(["local", "verify", str(enc), "--passphrase", "pw"])
    assert rc == 0

    # unseal -> stdout
    rc = main(["local", "unseal", str(enc), "--passphrase", "pw"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "platform: google" in out
