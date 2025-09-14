from __future__ import annotations

from typing import Any, Dict, List

from noctivault.core.errors import DuplicatePathError
from noctivault.core.value import SecretValue
from noctivault.provider.local_mocks import LocalMocksProvider
from noctivault.schema.models import SecretGroup, SecretRef, TopLevelConfig
from noctivault.tree.node import SecretNode


class SecretResolver:
    def __init__(self, provider: LocalMocksProvider):
        self.provider = provider

    def resolve(self, cfg: TopLevelConfig) -> SecretNode:
        refs: List[tuple[list[str], SecretRef]] = []
        if cfg.secret_refs:
            for entry in cfg.secret_refs:
                if isinstance(entry, SecretGroup):
                    for child in entry.children:
                        refs.append(([entry.key, child.cast], child))
                else:
                    assert isinstance(entry, SecretRef)
                    refs.append(([entry.cast], entry))

        out: Dict[str, Any] = {}
        for path_parts, ref in refs:
            # fetch raw
            raw = self.provider.fetch(ref.platform, ref.gcp_project_id, ref.ref, ref.version)
            # cast according to type (validate now), but store SecretValue to preserve raw
            val = SecretValue(raw, type_=ref.type or "str")
            _ = val.cast()  # validate cast here; raises TypeCastError on failure
            # place into nested dict
            self._place(out, path_parts, val)
        return SecretNode(out)

    def _place(self, tree: Dict[str, Any], path: list[str], value: SecretValue) -> None:
        cur = tree
        for part in path[:-1]:
            cur = cur.setdefault(part, {})
        leaf = path[-1]
        if leaf in cur:
            raise DuplicatePathError(".".join(path))
        cur[leaf] = value
