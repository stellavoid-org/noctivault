from __future__ import annotations

import logging
import time
from typing import Any, Callable, Literal, Optional

from noctivault.core.errors import (
    AuthorizationError,
    DecryptError,
    MissingDependencyError,
    MissingRemoteSecretError,
    RemoteArgumentError,
    RemoteDecodeError,
    RemoteUnavailableError,
)
from noctivault.schema.models import Platform


class GcpSecretManagerProvider:
    def __init__(
        self,
        client: Optional[Any] = None,
        gexc: Optional[Any] = None,
        sleeper: Optional[Callable[[float], None]] = None,
    ) -> None:
        if client is not None:
            # For tests: allow injecting a preconfigured client and optional exceptions module
            self._client = client
            self._gexc = gexc
            self._sleep = sleeper or time.sleep
            self._log = logging.getLogger("noctivault.provider.gcp")
            return
        try:  # lazy import to keep optional dependency
            from google.api_core import exceptions as _gexc
            from google.cloud import secretmanager as _secretmanager
        except Exception as exc:  # pragma: no cover - exercised when extra not installed
            raise MissingDependencyError(
                "google-cloud-secret-manager is required for GCP provider"
            ) from exc
        self._client = _secretmanager.SecretManagerServiceClient()
        self._gexc = _gexc
        self._sleep = time.sleep
        self._log = logging.getLogger("noctivault.provider.gcp")

    def fetch(
        self,
        platform: Platform,
        project: str,
        name: str,
        version: int | Literal["latest"],
    ) -> str:
        if platform is not Platform.GOOGLE:
            raise RemoteArgumentError("unsupported platform")
        ver = "latest" if version == "latest" else str(int(version))
        resource = f"projects/{project}/secrets/{name}/versions/{ver}"
        attempts = 0
        backoff_base = 0.2  # for 5xx
        backoff_429_base = 1.0  # for rate limiting
        while True:
            attempts += 1
            try:
                resp: Any = self._client.access_secret_version(name=resource)
                data: bytes = resp.payload.data
                break
            except Exception as exc:  # map known errors if available
                gexc = getattr(self, "_gexc", None)
                if gexc is not None:
                    # 404 NotFound: short retry once (total 2 attempts)
                    if isinstance(exc, getattr(gexc, "NotFound", ())):
                        if attempts <= 1:
                            delay = 0.2
                            if self._log.isEnabledFor(logging.WARNING):
                                self._log.warning(
                                    "GCP fetch retry (404): project=%s, secret=%s, version=%s, attempt=%d/%d, next_backoff=%.1fs, error=%s",
                                    project,
                                    name,
                                    f"{version}",
                                    attempts,
                                    1,
                                    delay,
                                    exc.__class__.__name__,
                                )
                            self._sleep(delay)
                            continue
                        if self._log.isEnabledFor(logging.ERROR):
                            self._log.error(
                                "GCP fetch failed (404): project=%s, secret=%s, version=%s",
                                project,
                                name,
                                f"{version}",
                            )
                        raise MissingRemoteSecretError((project, name, version)) from exc
                    # 5xx bucket: ServiceUnavailable, InternalServerError, BadGateway
                    if (
                        isinstance(exc, getattr(gexc, "ServiceUnavailable", ()))
                        or isinstance(exc, getattr(gexc, "InternalServerError", ()))
                        or isinstance(exc, getattr(gexc, "BadGateway", ()))
                    ):
                        if attempts <= 3:
                            delay = backoff_base * (2 ** (attempts - 1))
                            if self._log.isEnabledFor(logging.WARNING):
                                self._log.warning(
                                    "GCP fetch retry (5xx): project=%s, secret=%s, version=%s, attempt=%d/%d, next_backoff=%.1fs, error=%s",
                                    project,
                                    name,
                                    f"{version}",
                                    attempts,
                                    3,
                                    delay,
                                    exc.__class__.__name__,
                                )
                            self._sleep(delay)
                            continue
                        if self._log.isEnabledFor(logging.ERROR):
                            self._log.error(
                                "GCP fetch failed (5xx): project=%s, secret=%s, version=%s",
                                project,
                                name,
                                f"{version}",
                            )
                        raise RemoteUnavailableError(str(exc)) from exc
                    # 429 / rate limit: ResourceExhausted
                    if isinstance(exc, getattr(gexc, "ResourceExhausted", ())):
                        if attempts <= 3:
                            # Prefer RetryInfo if provided by gRPC error details
                            ri = getattr(exc, "retry_info", None)
                            if ri is not None and hasattr(ri, "seconds"):
                                sec = getattr(ri, "seconds", 0) or 0
                                nanos = getattr(ri, "nanos", 0) or 0
                                delay = float(sec) + float(nanos) / 1_000_000_000.0
                                # guard zero delay
                                if delay <= 0:
                                    delay = backoff_429_base * (2 ** (attempts - 1))
                            else:
                                delay = backoff_429_base * (2 ** (attempts - 1))
                            if self._log.isEnabledFor(logging.WARNING):
                                self._log.warning(
                                    "GCP fetch retry (429): project=%s, secret=%s, version=%s, attempt=%d/%d, next_backoff=%.1fs, error=%s, retry_info=%s",
                                    project,
                                    name,
                                    f"{version}",
                                    attempts,
                                    3,
                                    delay,
                                    exc.__class__.__name__,
                                    "yes" if ri is not None else "none",
                                )
                            self._sleep(delay)
                            continue
                        if self._log.isEnabledFor(logging.ERROR):
                            self._log.error(
                                "GCP fetch failed (429): project=%s, secret=%s, version=%s",
                                project,
                                name,
                                f"{version}",
                            )
                        raise RemoteUnavailableError(str(exc)) from exc
                    # Auth / input errors: no retry
                    if isinstance(
                        exc,
                        (
                            getattr(gexc, "PermissionDenied", ()),
                            getattr(gexc, "Unauthenticated", ()),
                        ),
                    ):
                        if self._log.isEnabledFor(logging.ERROR):
                            self._log.error(
                                "GCP fetch failed (auth): project=%s, secret=%s, version=%s, error=%s",
                                project,
                                name,
                                f"{version}",
                                exc.__class__.__name__,
                            )
                        raise AuthorizationError(str(exc)) from exc
                    if isinstance(exc, getattr(gexc, "InvalidArgument", ())) or isinstance(
                        exc, getattr(gexc, "FailedPrecondition", ())
                    ):
                        if self._log.isEnabledFor(logging.ERROR):
                            self._log.error(
                                "GCP fetch failed (argument): project=%s, secret=%s, version=%s, error=%s",
                                project,
                                name,
                                f"{version}",
                                exc.__class__.__name__,
                            )
                        raise RemoteArgumentError(str(exc)) from exc
                    if isinstance(exc, getattr(gexc, "DeadlineExceeded", ())) or isinstance(
                        exc, getattr(gexc, "GatewayTimeout", ())
                    ):
                        # treat as unavailable without retry (policy keeps retries to 5xx only)
                        if self._log.isEnabledFor(logging.ERROR):
                            self._log.error(
                                "GCP fetch failed (deadline): project=%s, secret=%s, version=%s, error=%s",
                                project,
                                name,
                                f"{version}",
                                exc.__class__.__name__,
                            )
                        raise RemoteUnavailableError(str(exc)) from exc
                # Unknown or unmapped error
                if self._log.isEnabledFor(logging.ERROR):
                    self._log.error(
                        "GCP fetch failed (unknown): project=%s, secret=%s, version=%s, error=%s",
                        project,
                        name,
                        f"{version}",
                        exc.__class__.__name__,
                    )
                raise DecryptError("remote access failed") from exc
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RemoteDecodeError("secret payload is not valid UTF-8") from exc
