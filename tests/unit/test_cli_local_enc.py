import os
import stat
import textwrap
from pathlib import Path

import pytest


def test_key_gen_default_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from noctivault.cli import key_gen

    # redirect HOME
    fake_home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(fake_home))

    out = key_gen(None)
    p = Path(out)
    assert p.exists()
    data = p.read_bytes()
    assert len(data) == 32
    mode = stat.S_IMODE(os.stat(p).st_mode)
    assert mode & (stat.S_IRWXG | stat.S_IRWXO) == 0  # no group/other perms


def test_seal_unseal_via_cli_helpers(tmp_path: Path):
    from noctivault.cli import key_gen, seal, unseal, verify

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

    key_path = key_gen(tmp_path / "local.key")

    enc_path = seal(tmp_path, key_file_path=key_path, out=None, rm_plain=False, force=True)
    assert Path(enc_path).exists()
    assert verify(enc_path, key_file_path=key_path) is True

    out_bytes = unseal(enc_path, key_file_path=key_path)
    assert out_bytes.decode("utf-8").lstrip().startswith("platform: google")


def test_seal_rm_plain_and_force(tmp_path: Path):
    from noctivault.cli import key_gen, seal

    plain = tmp_path / "noctivault.local-store.yaml"
    plain.write_text("platform: google\ngcp_project_id: p\n", encoding="utf-8")
    key_path = key_gen(tmp_path / "k.key")

    # first seal creates enc and leaves plain when rm_plain=False
    enc1 = seal(tmp_path, key_file_path=key_path, rm_plain=False, force=False)
    assert Path(enc1).exists()
    assert plain.exists()

    # second seal without force should fail
    with pytest.raises(FileExistsError):
        seal(tmp_path, key_file_path=key_path)

    # force overwrite, rm_plain removes plaintext
    enc2 = seal(tmp_path, key_file_path=key_path, rm_plain=True, force=True)
    assert Path(enc2).exists()
    assert not plain.exists()
