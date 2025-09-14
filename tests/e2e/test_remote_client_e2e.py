import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_remote_client_loads_from_refs_only_with_mock_provider(monkeypatch, tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings

    # write refs only
    (tmp_path / "noctivault.yaml").write_text(
        textwrap.dedent(
            """
            platform: google
            gcp_project_id: p
            secret-refs:
              - cast: password
                ref: pw
                version: 1
              - key: database
                children:
                  - cast: port
                    ref: port
                    version: latest
                    type: int
            """
        ),
        encoding="utf-8",
    )

    # mock provider
    class _FakeProvider:
        def __init__(self) -> None:
            self.calls = []

        def fetch(self, platform, project, name, version):
            self.calls.append((platform, project, name, version))
            if name == "pw":
                return "secret"
            if name == "port":
                return "5432"
            raise AssertionError("unexpected secret name")

    def _fake_ctor():
        return _FakeProvider()

    monkeypatch.setattr("noctivault.client.GcpSecretManagerProvider", _fake_ctor)

    nv = Noctivault(NoctivaultSettings(source="remote"))
    secrets = nv.load(local_store_path=str(tmp_path))

    assert secrets.password.get() == "secret"
    assert secrets.database.port.get() == "5432"
    # types propagated in to_dict reveal
    assert secrets.to_dict(reveal=True)["database"]["port"] == 5432
