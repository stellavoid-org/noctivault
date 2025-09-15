from __future__ import annotations

from typing import Literal, Protocol

from noctivault.schema.models import Platform


class SecretProviderProtocol(Protocol):
    def fetch(
        self, platform: Platform, project: str, name: str, version: int | Literal["latest"]
    ) -> str: ...
