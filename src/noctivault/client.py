from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, TYPE_CHECKING

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from noctivault.tree.node import SecretNode

from noctivault.app.resolver import SecretResolver
from noctivault.io.fs import resolve_local_store_path
from noctivault.io.yaml import read_yaml
from noctivault.provider.local_mocks import LocalMocksProvider
from noctivault.schema.models import TopLevelConfig


class NoctivaultSettings(BaseModel):
    source: str = "local"


@dataclass
class Noctivault:
    settings: NoctivaultSettings
    _secrets: Any | None = None
    _raw_index: dict[str, str] | None = None  # path -> raw string for display_hash
    _type_index: dict[str, str] | None = None  # path -> type ("str"|"int")

    def load(self, local_store_path: str = "../") -> "SecretNode":
        if self.settings.source != "local":
            raise NotImplementedError("remote source not implemented")
        cfg_path = resolve_local_store_path(local_store_path)
        data = read_yaml(cfg_path)
        cfg = TopLevelConfig.model_validate(data)

        provider = LocalMocksProvider.from_config(cfg)
        resolver = SecretResolver(provider)
        node = resolver.resolve(cfg)

        # also build indices for get/display_hash
        raw_index: dict[str, str] = {}
        type_index: dict[str, str] = {}

        def walk(prefix: list[str], obj: Any) -> None:
            from noctivault.core.value import SecretValue
            from noctivault.tree.node import SecretNode

            if isinstance(obj, SecretNode):
                # traverse internal mapping via typed accessor
                for k, v in obj._as_mapping().items():
                    walk(prefix + [k], v)
                return
            if isinstance(obj, dict):
                for k, v in obj.items():
                    walk(prefix + [k], v)
                return
            if isinstance(obj, SecretValue):
                path = ".".join(prefix)
                raw_index[path] = obj.get()
                type_index[path] = obj._type

        walk([], node)
        self._secrets = node
        self._raw_index = raw_index
        self._type_index = type_index
        return node

    def _ensure_loaded(self) -> None:
        if self._secrets is None:
            raise RuntimeError("secrets not loaded; call load() first")

    def get(self, path: str) -> Any:
        self._ensure_loaded()
        assert (
            self._secrets is not None
            and self._raw_index is not None
            and self._type_index is not None
        )
        if path not in self._raw_index:
            raise KeyError(path)
        raw = self._raw_index[path]
        t = self._type_index[path]
        if t == "str":
            return raw
        if t == "int":
            return int(raw)
        return raw

    def display_hash(self, path: str) -> str:
        self._ensure_loaded()
        assert self._raw_index is not None
        try:
            raw = self._raw_index[path]
        except KeyError as exc:
            raise KeyError(path) from exc
        return hashlib.sha3_256(raw.encode("utf-8")).hexdigest()


def noctivault(settings: NoctivaultSettings) -> Noctivault:
    return Noctivault(settings)
