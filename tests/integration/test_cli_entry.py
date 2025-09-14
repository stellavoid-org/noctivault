import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.integration


def test_cli_key_gen_seal_verify_unseal(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    from noctivault.cli import main

    # make HOME deterministic
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))

    # generate key
    key_path = tmp_path / "k.key"
    rc = main(["key", "gen", "--out", str(key_path)])
    assert rc == 0
    assert key_path.exists() and key_path.read_bytes()

    # write plaintext yaml in tmp dir
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

    # seal
    rc = main(["local", "seal", str(tmp_path), "--key-file", str(key_path)])
    assert rc == 0
    enc = tmp_path / "noctivault.local-store.yaml.enc"
    assert enc.exists()

    # verify
    rc = main(["local", "verify", str(enc), "--key-file", str(key_path)])
    assert rc == 0

    # unseal -> stdout
    rc = main(["local", "unseal", str(enc), "--key-file", str(key_path)])
    out = capsys.readouterr().out
    assert rc == 0
    assert "platform: google" in out
