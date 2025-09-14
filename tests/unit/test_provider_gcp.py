import types
from unittest.mock import create_autospec

import pytest

pytestmark = pytest.mark.unit


class _Resp:
    def __init__(self, data: bytes):
        class _Payload:
            def __init__(self, d: bytes) -> None:
                self.data = d

        self.payload = _Payload(data)


class _Client:
    def access_secret_version(self, name: str):  # pragma: no cover - interface only
        ...


def test_gcp_provider_fetch_version_and_latest_and_decode_utf8():
    from noctivault.provider.gcp import GcpSecretManagerProvider
    from noctivault.schema.models import Platform

    client = create_autospec(_Client, instance=True, spec_set=True)
    client.access_secret_version.return_value = _Resp(b"hello")

    provider = GcpSecretManagerProvider(client=client, gexc=None)

    v1 = provider.fetch(Platform.GOOGLE, "p", "n", 1)
    latest = provider.fetch(Platform.GOOGLE, "p", "n", "latest")

    assert v1 == "hello"
    assert latest == "hello"

    # name formatting
    client.access_secret_version.assert_any_call(name="projects/p/secrets/n/versions/1")
    client.access_secret_version.assert_any_call(name="projects/p/secrets/n/versions/latest")


def _gexc_namespace():
    # Build a namespace with exception types similar to google.api_core.exceptions
    class NotFound(Exception):
        pass

    class PermissionDenied(Exception):
        pass

    class Unauthenticated(Exception):
        pass

    class InvalidArgument(Exception):
        pass

    class DeadlineExceeded(Exception):
        pass

    class ServiceUnavailable(Exception):
        pass

    return types.SimpleNamespace(
        NotFound=NotFound,
        PermissionDenied=PermissionDenied,
        Unauthenticated=Unauthenticated,
        InvalidArgument=InvalidArgument,
        DeadlineExceeded=DeadlineExceeded,
        ServiceUnavailable=ServiceUnavailable,
    )


def test_gcp_provider_error_mappings():
    from noctivault.core.errors import (
        AuthorizationError,
        MissingRemoteSecretError,
        RemoteArgumentError,
        RemoteDecodeError,
        RemoteUnavailableError,
    )
    from noctivault.provider.gcp import GcpSecretManagerProvider
    from noctivault.schema.models import Platform

    gexc = _gexc_namespace()

    # not found
    client = create_autospec(_Client, instance=True, spec_set=True)
    client.access_secret_version.side_effect = gexc.NotFound()
    provider = GcpSecretManagerProvider(client=client, gexc=gexc)
    with pytest.raises(MissingRemoteSecretError):
        provider.fetch(Platform.GOOGLE, "p", "n", 1)

    # permission
    client = create_autospec(_Client, instance=True, spec_set=True)
    client.access_secret_version.side_effect = gexc.PermissionDenied()
    provider = GcpSecretManagerProvider(client=client, gexc=gexc)
    with pytest.raises(AuthorizationError):
        provider.fetch(Platform.GOOGLE, "p", "n", 1)

    # invalid argument
    client = create_autospec(_Client, instance=True, spec_set=True)
    client.access_secret_version.side_effect = gexc.InvalidArgument()
    provider = GcpSecretManagerProvider(client=client, gexc=gexc)
    with pytest.raises(RemoteArgumentError):
        provider.fetch(Platform.GOOGLE, "p", "n", 1)

    # service unavailable
    client = create_autospec(_Client, instance=True, spec_set=True)
    client.access_secret_version.side_effect = gexc.ServiceUnavailable()
    provider = GcpSecretManagerProvider(client=client, gexc=gexc)
    with pytest.raises(RemoteUnavailableError):
        provider.fetch(Platform.GOOGLE, "p", "n", 1)

    # non-utf8 decode
    client = create_autospec(_Client, instance=True, spec_set=True)
    client.access_secret_version.return_value = _Resp(b"\xff\xfe\x00")
    provider = GcpSecretManagerProvider(client=client, gexc=gexc)
    with pytest.raises(RemoteDecodeError):
        provider.fetch(Platform.GOOGLE, "p", "n", 1)
