import textwrap
from pathlib import Path

import pytest

pytestmark = pytest.mark.e2e


def test_remote_missing_reference_file_raises(tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings

    # no noctivault.yaml present
    nv = Noctivault(NoctivaultSettings(source="remote"))
    with pytest.raises(FileNotFoundError):
        nv.load(local_store_path=str(tmp_path))


def test_remote_ignores_local_mocks_present(monkeypatch, tmp_path: Path):
    from noctivault.client import Noctivault, NoctivaultSettings

    # create a local mocks file that would be ignored
    (tmp_path / "noctivault.local-store.yaml").write_text(
        textwrap.dedent(
            """
            platform: google
            gcp_project_id: wrong
            secret-mocks:
              - name: pw
                value: wrong
                version: 1
            """
        ),
        encoding="utf-8",
    )

    # write refs which remote should use
    (tmp_path / "noctivault.yaml").write_text(
        textwrap.dedent(
            """
            platform: google
            gcp_project_id: p
            secret-refs:
              - cast: password
                ref: pw
                version: 1
            """
        ),
        encoding="utf-8",
    )

    class _FakeProvider:
        def fetch(self, platform, project, name, version):
            assert project == "p"
            if name == "pw":
                return "secret"
            raise AssertionError("unexpected secret name")

    monkeypatch.setattr("noctivault.client.GcpSecretManagerProvider", lambda: _FakeProvider())

    nv = Noctivault(NoctivaultSettings(source="remote"))
    secrets = nv.load(local_store_path=str(tmp_path))
    assert secrets.password.get() == "secret"
