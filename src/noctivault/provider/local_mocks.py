from __future__ import annotations

from collections import defaultdict
from typing import Dict, Tuple, Union

from noctivault.core.errors import MissingLocalMockError
from noctivault.schema.models import TopLevelConfig

Key = Tuple[str, str, str]  # (platform, project, name)


class LocalMocksProvider:
    def __init__(self, index: Dict[Key, Dict[int, str]]):
        self._index = index

    @classmethod
    def from_config(cls, cfg: TopLevelConfig) -> "LocalMocksProvider":
        idx: Dict[Key, Dict[int, str]] = defaultdict(dict)
        for m in cfg.secret_mocks:
            plat = m.effective_platform
            proj = m.effective_project
            key: Key = (plat, proj, m.name)
            idx[key][m.version] = m.value
        return cls(index=dict(idx))

    def fetch(self, platform: str, project: str, name: str, version: Union[int, str]) -> str:
        key: Key = (platform, project, name)
        versions = self._index.get(key)
        if not versions:
            raise MissingLocalMockError(key)
        if version == "latest":
            resolved = max(versions.keys())
        else:
            assert isinstance(version, int)
            resolved = version
        try:
            return versions[resolved]
        except KeyError as exc:
            raise MissingLocalMockError((key, resolved)) from exc
