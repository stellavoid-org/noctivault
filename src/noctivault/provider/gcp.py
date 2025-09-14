from __future__ import annotations

from typing import Any, Literal, Optional

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
    def __init__(self, client: Optional[Any] = None, gexc: Optional[Any] = None) -> None:
        if client is not None:
            # For tests: allow injecting a preconfigured client and optional exceptions module
            self._client = client
            self._gexc = gexc
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
        try:
            resp: Any = self._client.access_secret_version(name=resource)
            data: bytes = resp.payload.data
        except Exception as exc:  # map known errors if available
            gexc = getattr(self, "_gexc", None)
            if gexc is not None:
                if isinstance(exc, gexc.NotFound):
                    raise MissingRemoteSecretError((project, name, version)) from exc
                if isinstance(exc, (gexc.PermissionDenied, gexc.Unauthenticated)):
                    raise AuthorizationError(str(exc)) from exc
                if isinstance(exc, gexc.InvalidArgument):
                    raise RemoteArgumentError(str(exc)) from exc
                if isinstance(exc, (gexc.DeadlineExceeded, gexc.ServiceUnavailable)):
                    raise RemoteUnavailableError(str(exc)) from exc
            raise DecryptError("remote access failed") from exc
        try:
            return data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RemoteDecodeError("secret payload is not valid UTF-8") from exc
