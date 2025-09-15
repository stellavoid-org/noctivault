import secrets
import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


YAML_BASE = textwrap.dedent(
    """
    platform: google
    gcp_project_id: p
    secret-mocks:
      - name: x
        value: "00123"
        version: 1
    """
).encode("utf-8")


def write_enc(tmp: Path, key: bytes) -> None:
    from noctivault.io.enc import seal_with_key

    (tmp / "noctivault.local-store.yaml.enc").write_bytes(seal_with_key(YAML_BASE, key))


def test_key_resolution_settings_path(tmp_path: Path):
    from noctivault.client import LocalEncSettings, Noctivault, NoctivaultSettings

    key = secrets.token_bytes(32)
    key_path = tmp_path / "custom.key"
    key_path.write_bytes(key)
    write_enc(tmp_path, key)
    # refs
    (tmp_path / "noctivault.yaml").write_text(
        textwrap.dedent(
            """
            platform: google
            gcp_project_id: p
            secret-refs:
              - cast: password
                ref: x
                version: 1
            """
        ),
        encoding="utf-8",
    )

    nv = Noctivault(
        NoctivaultSettings(source="local", local_enc=LocalEncSettings(key_file_path=str(key_path)))
    )
    s = nv.load(local_store_path=str(tmp_path))
    assert s.password.get() == "00123"


def test_key_resolution_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from noctivault.client import Noctivault, NoctivaultSettings

    key = secrets.token_bytes(32)
    key_path = tmp_path / "env.key"
    key_path.write_bytes(key)
    write_enc(tmp_path, key)
    (tmp_path / "noctivault.yaml").write_text(
        "platform: google\ngcp_project_id: p\nsecret-refs:\n- cast: password\n  ref: x\n  version: 1\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("NOCTIVAULT_LOCAL_KEY_FILE", str(key_path))
    nv = Noctivault(NoctivaultSettings(source="local"))
    s = nv.load(local_store_path=str(tmp_path))
    assert s.password.get() == "00123"


def test_key_resolution_local_file(tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings

    key = secrets.token_bytes(32)
    (tmp_path / "local.key").write_bytes(key)
    write_enc(tmp_path, key)
    (tmp_path / "noctivault.yaml").write_text(
        "platform: google\ngcp_project_id: p\nsecret-refs:\n- cast: password\n  ref: x\n  version: 1\n",
        encoding="utf-8",
    )

    nv = Noctivault(NoctivaultSettings(source="local"))
    s = nv.load(local_store_path=str(tmp_path))
    assert s.password.get() == "00123"


def test_key_resolution_default_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    from noctivault.client import Noctivault, NoctivaultSettings

    key = secrets.token_bytes(32)
    # create fake home with default key path
    fake_home = tmp_path / "home"
    cfg_dir = fake_home / ".config" / "noctivault"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "local.key").write_bytes(key)
    write_enc(tmp_path, key)
    (tmp_path / "noctivault.yaml").write_text(
        "platform: google\ngcp_project_id: p\nsecret-refs:\n- cast: password\n  ref: x\n  version: 1\n",
        encoding="utf-8",
    )

    monkeypatch.setenv("HOME", str(fake_home))
    nv = Noctivault(NoctivaultSettings(source="local"))
    s = nv.load(local_store_path=str(tmp_path))
    assert s.password.get() == "00123"


def test_wrong_key_raises(tmp_path: Path):
    from noctivault.client import LocalEncSettings, Noctivault, NoctivaultSettings
    from noctivault.core.errors import DecryptError

    key = secrets.token_bytes(32)
    wrong = secrets.token_bytes(32)
    wrong_path = tmp_path / "wrong.key"
    wrong_path.write_bytes(wrong)
    write_enc(tmp_path, key)
    (tmp_path / "noctivault.yaml").write_text(
        "platform: google\ngcp_project_id: p\nsecret-refs:\n- cast: password\n  ref: x\n  version: 1\n",
        encoding="utf-8",
    )

    nv = Noctivault(
        NoctivaultSettings(
            source="local", local_enc=LocalEncSettings(key_file_path=str(wrong_path))
        )
    )
    with pytest.raises(DecryptError):
        nv.load(local_store_path=str(tmp_path))
