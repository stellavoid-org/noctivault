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

    class InternalServerError(Exception):
        pass

    class BadGateway(Exception):
        pass

    class ResourceExhausted(Exception):
        def __init__(self, retry_info=None):
            super().__init__("rate limited")
            self.retry_info = retry_info

    return types.SimpleNamespace(
        NotFound=NotFound,
        PermissionDenied=PermissionDenied,
        Unauthenticated=Unauthenticated,
        InvalidArgument=InvalidArgument,
        DeadlineExceeded=DeadlineExceeded,
        ServiceUnavailable=ServiceUnavailable,
        InternalServerError=InternalServerError,
        BadGateway=BadGateway,
        ResourceExhausted=ResourceExhausted,
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


def test_gcp_provider_retries_not_found_once_then_succeeds():
    from noctivault.provider.gcp import GcpSecretManagerProvider
    from noctivault.schema.models import Platform

    gexc = _gexc_namespace()
    client = create_autospec(_Client, instance=True, spec_set=True)

    seq = [gexc.NotFound(), _Resp(b"ok")]

    def _call(name: str):
        exc_or_resp = seq.pop(0)
        if isinstance(exc_or_resp, Exception):
            raise exc_or_resp
        return exc_or_resp

    client.access_secret_version.side_effect = _call
    calls = {"n": 0}

    def _sleep(_):
        calls["n"] += 1

    provider = GcpSecretManagerProvider(client=client, gexc=gexc, sleeper=_sleep)
    out = provider.fetch(Platform.GOOGLE, "p", "n", "latest")
    assert out == "ok"
    # one sleep indicates one retry
    assert calls["n"] == 1
    assert client.access_secret_version.call_count == 2


def test_gcp_provider_retries_5xx_with_backoff():
    from noctivault.provider.gcp import GcpSecretManagerProvider
    from noctivault.schema.models import Platform

    gexc = _gexc_namespace()
    client = create_autospec(_Client, instance=True, spec_set=True)

    seq = [gexc.ServiceUnavailable(), gexc.InternalServerError(), _Resp(b"ok")]

    def _call(name: str):
        exc_or_resp = seq.pop(0)
        if isinstance(exc_or_resp, Exception):
            raise exc_or_resp
        return exc_or_resp

    client.access_secret_version.side_effect = _call
    sleeps: list[float] = []

    def _sleep(d: float):
        sleeps.append(d)

    provider = GcpSecretManagerProvider(client=client, gexc=gexc, sleeper=_sleep)
    out = provider.fetch(Platform.GOOGLE, "p", "n", 1)
    assert out == "ok"
    # two retries -> two sleeps with exponential pattern (0.2, 0.4)
    assert len(sleeps) == 2
    assert sleeps[0] == pytest.approx(0.2, rel=1e-6)
    assert sleeps[1] == pytest.approx(0.4, rel=1e-6)
    assert client.access_secret_version.call_count == 3


def test_gcp_provider_retries_429_with_backoff_when_no_retry_info():
    from noctivault.provider.gcp import GcpSecretManagerProvider
    from noctivault.schema.models import Platform

    gexc = _gexc_namespace()
    client = create_autospec(_Client, instance=True, spec_set=True)

    seq = [
        gexc.ResourceExhausted(),
        gexc.ResourceExhausted(),
        _Resp(b"ok"),
    ]  # success after 2 retries

    def _call(name: str):
        exc_or_resp = seq.pop(0)
        if isinstance(exc_or_resp, Exception):
            raise exc_or_resp
        return exc_or_resp

    client.access_secret_version.side_effect = _call
    sleeps: list[float] = []

    def _sleep(d: float):
        sleeps.append(d)

    provider = GcpSecretManagerProvider(client=client, gexc=gexc, sleeper=_sleep)
    out = provider.fetch(Platform.GOOGLE, "p", "n", 1)
    assert out == "ok"
    # two retries -> backoff 1.0, 2.0
    assert sleeps == [pytest.approx(1.0, rel=1e-6), pytest.approx(2.0, rel=1e-6)]


def test_gcp_provider_retries_429_respects_retry_info():
    from noctivault.provider.gcp import GcpSecretManagerProvider
    from noctivault.schema.models import Platform

    class _RI:
        def __init__(self, s: int, n: int) -> None:
            self.seconds = s
            self.nanos = n

    gexc = _gexc_namespace()
    client = create_autospec(_Client, instance=True, spec_set=True)

    seq = [gexc.ResourceExhausted(_RI(0, 500_000_000)), _Resp(b"ok")]  # 0.5 sec recommended

    def _call(name: str):
        exc_or_resp = seq.pop(0)
        if isinstance(exc_or_resp, Exception):
            raise exc_or_resp
        return exc_or_resp

    client.access_secret_version.side_effect = _call
    sleeps: list[float] = []

    def _sleep(d: float):
        sleeps.append(d)

    provider = GcpSecretManagerProvider(client=client, gexc=gexc, sleeper=_sleep)
    out = provider.fetch(Platform.GOOGLE, "p", "n", 1)
    assert out == "ok"
    assert len(sleeps) == 1
    assert sleeps[0] == pytest.approx(0.5, rel=1e-6)
