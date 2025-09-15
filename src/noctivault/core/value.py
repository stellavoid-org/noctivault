from __future__ import annotations

from typing import Any, Literal

from noctivault.core.errors import TypeCastError
from pydantic import SecretStr

AllowedType = Literal["str", "int"]


class SecretValue:
    def __init__(self, raw: str, type_: AllowedType = "str"):
        self._raw = raw
        self._type = type_
        self._secret = SecretStr(raw)

    def get(self) -> str:
        # raw string value
        return self._secret.get_secret_value()

    def cast(self) -> Any:
        if self._type == "str":
            return str(self._raw)
        if self._type == "int":
            try:
                return int(self._raw)
            except Exception as exc:
                raise TypeCastError(self._raw) from exc
        # should not happen due to schema validation
        return self._raw

    def equals(self, candidate: str) -> bool:
        if self._type == "str":
            return str(candidate) == self._raw
        if self._type == "int":
            try:
                # Compare as integers without relying on Any-typed cast()
                return int(candidate) == int(self._raw)
            except Exception as exc:
                raise TypeCastError(candidate) from exc
        return False

    def __repr__(self) -> str:  # masked
        return "***"

    __str__ = __repr__
