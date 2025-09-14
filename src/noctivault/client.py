from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, Optional

from pydantic import BaseModel

if TYPE_CHECKING:  # pragma: no cover - typing only
    from noctivault.tree.node import SecretNode

from noctivault.app.resolver import SecretResolver
from noctivault.core.errors import CombinedConfigNotAllowedError, MissingKeyMaterialError
from noctivault.io.enc import unseal_with_key, unseal_with_passphrase
from noctivault.io.fs import resolve_local_store_source, resolve_reference_path
from noctivault.io.yaml import read_yaml, read_yaml_text
from noctivault.provider.local_mocks import LocalMocksProvider
from noctivault.schema.models import ReferenceConfig, TopLevelConfig


class LocalEncSettings(BaseModel):
    mode: Literal["key-file", "passphrase"] = "key-file"
    key_file_path: Optional[str] = None
    passphrase: Optional[str] = None  # tests convenience; prefer provider/secure input in real use


class NoctivaultSettings(BaseModel):
    source: str = "local"
    local_enc: Optional[LocalEncSettings] = None


@dataclass
class Noctivault:
    settings: NoctivaultSettings
    _secrets: Any | None = None
    _raw_index: dict[str, str] | None = None  # path -> raw string for display_hash
    _type_index: dict[str, str] | None = None  # path -> type ("str"|"int")

    def load(
        self, local_store_path: str = "../", reference_path: Optional[str] = None
    ) -> "SecretNode":
        if self.settings.source != "local":
            raise NotImplementedError("remote source not implemented")
        kind, path = resolve_local_store_source(local_store_path)
        # resolve reference file alongside mocks unless explicitly specified
        ref_path = reference_path or resolve_reference_path(Path(path).parent.as_posix())
        if kind == "yaml":
            data = read_yaml(path)
        else:
            # enc: load key and decrypt
            enc_bytes = Path(path).read_bytes()
            # choose passphrase or key-file
            if self._use_passphrase():
                pw = self._load_local_passphrase()
                plain = unseal_with_passphrase(enc_bytes, pw)
            else:
                key = self._load_local_key(Path(path).parent)
                plain = unseal_with_key(enc_bytes, key)
            data = read_yaml_text(plain.decode("utf-8"))
        if data.get("secret-refs"):
            raise CombinedConfigNotAllowedError("mocks file must not contain secret-refs")
        cfg = TopLevelConfig.model_validate(data)

        refs_data = read_yaml(ref_path)
        if refs_data.get("secret-mocks"):
            raise CombinedConfigNotAllowedError("reference file must not contain secret-mocks")
        refs_cfg = ReferenceConfig.model_validate(refs_data)

        provider = LocalMocksProvider.from_config(cfg)
        resolver = SecretResolver(provider)
        node = resolver.resolve(refs_cfg.secret_refs)

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

    def _load_local_key(self, directory: Path) -> bytes:
        # Priority: explicit in settings -> env -> local file -> default config path
        # 1) settings
        s = self.settings.local_enc
        if s and s.key_file_path:
            p = Path(s.key_file_path)
            return p.read_bytes()
        # 2) env var
        env = os.getenv("NOCTIVAULT_LOCAL_KEY_FILE")
        if env:
            return Path(env).expanduser().read_bytes()
        # 3) local file next to .enc
        local = directory / "local.key"
        if local.exists():
            return local.read_bytes()
        # 4) default config path
        default = Path.home() / ".config" / "noctivault" / "local.key"
        if default.exists():
            return default.read_bytes()
        raise MissingKeyMaterialError("local key file not found")

    def _use_passphrase(self) -> bool:
        s = self.settings.local_enc
        if s and s.mode == "passphrase":
            return True
        if os.getenv("NOCTIVAULT_LOCAL_PASSPHRASE"):
            return True
        return False

    def _load_local_passphrase(self) -> str:
        s = self.settings.local_enc
        if s and s.passphrase:
            return s.passphrase
        env = os.getenv("NOCTIVAULT_LOCAL_PASSPHRASE")
        if env:
            return env
        raise MissingKeyMaterialError("passphrase not provided")

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
