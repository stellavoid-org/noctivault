from __future__ import annotations

from typing import Any, Dict

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

        return walk(self._data)

    def __repr__(self) -> str:
        return f"SecretNode({self.to_dict(False)})"

    __str__ = __repr__
