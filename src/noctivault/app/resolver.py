from __future__ import annotations

from typing import Any, Dict, List

from noctivault.core.errors import DuplicatePathError
from noctivault.core.value import SecretValue
from noctivault.provider.local_mocks import LocalMocksProvider
from noctivault.schema.models import SecretGroup, SecretRef
from noctivault.tree.node import SecretNode


class SecretResolver:
    def __init__(self, provider: LocalMocksProvider):
        self.provider = provider

    def resolve(self, refs_config: List[SecretRef | SecretGroup]) -> SecretNode:
        refs_flat: List[tuple[list[str], SecretRef]] = []
        for entry in refs_config:
            if isinstance(entry, SecretGroup):
                for child in entry.children:
                    refs_flat.append(([entry.key, child.cast], child))
            else:
                assert isinstance(entry, SecretRef)
                refs_flat.append(([entry.cast], entry))

        out: Dict[str, Any] = {}
        for path_parts, ref in refs_flat:
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
