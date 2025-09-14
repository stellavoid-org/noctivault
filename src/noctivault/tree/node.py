from __future__ import annotations

from typing import Any, Dict, Mapping, cast

from noctivault.core.value import SecretValue
from pydantic import SecretStr


class _LeafProxy:
    def __init__(self, value: SecretValue):
        self._value = value

    def get(self) -> str:
        return self._value.get()

    def equals(self, candidate: str) -> bool:
        return self._value.equals(candidate)

    def __repr__(self) -> str:
        return "***"

    __str__ = __repr__


class SecretNode:
    def __init__(self, data: Dict[str, Any]):
        self._data = data

    def __getattr__(self, key: str) -> Any:
        v = self._data[key]
        if isinstance(v, dict):
            return SecretNode(v)
        if isinstance(v, SecretValue):
            return _LeafProxy(v)
        return v

    def __getitem__(self, key: str) -> Any:
        return getattr(self, key)

    def _as_mapping(self) -> Mapping[str, Any]:
        """Internal typed accessor for underlying mapping used by the client walker.
        Exposes a read-only view to satisfy type-checker without touching private fields.
        """
        return self._data

    def to_dict(self, reveal: bool = False) -> Dict[str, Any]:
        def walk(x: Any) -> Any:
            if isinstance(x, dict):
                return {k: walk(v) for k, v in x.items()}
            if isinstance(x, SecretValue):
                return x.cast() if reveal else "***"
            if isinstance(x, SecretStr):
                # not expected in new design, but keep compatibility
                return x.get_secret_value() if reveal else "***"
            return x

        # walk returns Any by construction; result is a nested dict[str, Any].
        # Narrow the type for callers. This is safe because branches return dicts.
        return cast(Dict[str, Any], walk(self._data))

    def __repr__(self) -> str:
        return f"SecretNode({self.to_dict(False)})"

    __str__ = __repr__
