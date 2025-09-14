from __future__ import annotations

from enum import Enum
from typing import Any, Literal, Optional

from noctivault.core.errors import CombinedConfigNotAllowedError
from pydantic import BaseModel, Field, model_validator

AllowedType = Literal["str", "int"]


class Platform(str, Enum):
    GOOGLE = "google"


class SecretMock(BaseModel):
    platform: Optional[Platform] = None
    gcp_project_id: Optional[str] = None
    name: str
    value: Any
    version: int

    @property
    def effective_platform(self) -> Platform:
        # Runtime-filled by TopLevelConfig validation context via inheritance.
        # TopLevelConfig requires platform, so the effective value is always str here.
        v = getattr(self, "_effective_platform", self.platform)
        assert isinstance(v, Platform)
        return v

    @property
    def effective_project(self) -> str:
        # See note above: TopLevelConfig requires gcp_project_id; cast to str is safe.
        v = getattr(self, "_effective_project", self.gcp_project_id)
        assert isinstance(v, str)
        return v

    @model_validator(mode="after")
    def _coerce_value_to_str(self) -> "SecretMock":
        # Accept any YAML scalar and coerce to string for storage
        if not isinstance(self.value, str):
            self.value = str(self.value)
        return self


class SecretRef(BaseModel):
    platform: Platform
    gcp_project_id: str
    cast: str  # leaf key name
    ref: str
    version: int | Literal["latest"] = "latest"
    type: AllowedType | None = None

    @model_validator(mode="after")
    def _default_type(self) -> "SecretRef":
        if self.type is None:
            self.type = "str"
        return self

    @model_validator(mode="after")
    def _validate_platform(self) -> "SecretRef":
        # Restrict current implementation to Google only
        if self.platform != Platform.GOOGLE:
            raise ValueError("unsupported platform")
        return self

    # version has a concrete default; no after-validator needed


class SecretGroup(BaseModel):
    key: str
    children: list[SecretRef]


class TopLevelConfig(BaseModel):
    platform: Platform
    gcp_project_id: str
    secret_mocks: list[SecretMock] = Field(default_factory=list, alias="secret-mocks")
    # secret-refs は TopLevelConfig では受け付けない（分離仕様）
    secret_refs: list[SecretRef | SecretGroup] | None = Field(default=None, alias="secret-refs")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def _apply_inheritance(self) -> "TopLevelConfig":
        # 同一ファイル構成を禁止
        if self.secret_refs is not None:
            raise CombinedConfigNotAllowedError(
                "TopLevelConfig must not contain secret-refs; use ReferenceConfig in noctivault.yaml"
            )
        # Fill effective platform/project on mocks where not specified
        for m in self.secret_mocks:
            eff_plat = m.platform or self.platform
            eff_proj = m.gcp_project_id or self.gcp_project_id
            # attach as private attrs for tests to check
            object.__setattr__(m, "_effective_platform", eff_plat)
            object.__setattr__(m, "_effective_project", eff_proj)

        return self


class ReferenceConfig(BaseModel):
    platform: Platform
    gcp_project_id: str
    secret_refs: list[SecretRef | SecretGroup] = Field(alias="secret-refs")

    model_config = {
        "populate_by_name": True,
        "extra": "ignore",
    }

    @model_validator(mode="before")
    @classmethod
    def _inherit_top_level(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        plat = data.get("platform")
        proj = data.get("gcp_project_id")
        refs = data.get("secret-refs")
        if isinstance(refs, list) and plat and proj:
            new_refs: list[Any] = []
            for entry in refs:
                if not isinstance(entry, dict):
                    new_refs.append(entry)
                    continue
                if "key" in entry and "children" in entry and isinstance(entry["children"], list):
                    children = []
                    for ch in entry["children"]:
                        if isinstance(ch, dict):
                            ch = {**ch}
                            ch.setdefault("platform", plat)
                            ch.setdefault("gcp_project_id", proj)
                        children.append(ch)
                    entry = {**entry, "children": children}
                else:
                    e = {**entry}
                    e.setdefault("platform", plat)
                    e.setdefault("gcp_project_id", proj)
                    entry = e
                new_refs.append(entry)
            data = {**data, "secret-refs": new_refs}
        return data

    @model_validator(mode="after")
    def _validate_platform(self) -> "ReferenceConfig":
        if self.platform != Platform.GOOGLE:
            raise ValueError("unsupported platform")
        # Children SecretRef validator enforces per-entry as well.
        return self
