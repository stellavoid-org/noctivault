# Noctivault

Noctivault は、クラウドの Secret Manager から環境変数を介さずにシークレットをプロセス内メモリへ安全に読み込む Python ライブラリです。設定と実行を分離し、値は既定でマスク表示されます。

## Install

```bash
pip install noctivault  # package name TBD
```

## Quickstart

```python
from noctivault import NoctivaultSettings
import noctivault  # provides factory `noctivault()` at top-level

nv = noctivault.noctivault(settings=NoctivaultSettings(source="local"))
secrets = nv.load(local_store_path="../")  # dir -> looks for noctivault.local-store.yaml

# Access masked values
print(secrets.database.password)      # -> ***
real = secrets.database.password.get()  # -> str
```

YAML スキーマ（refs/mocks・解決フロー・入力制約など）の詳細は docs/api.md を参照してください。

- ドキュメント: docs/api.md

## Status

MVP / Draft。`source: local` のみ実装（remote は予約）。仕様は docs/api.md を正とします。

## License

See LICENSE.
