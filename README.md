# Noctivault

Noctivault は、クラウドの Secret Manager から環境変数を介さずにシークレットをプロセス内メモリへ安全に読み込む Python ライブラリです。設定と実行を分離し、値は既定でマスク表示されます。

## Install

```bash
pip install noctivault                 # package name TBD
# 暗号化ローカルストア（.yaml.enc）を使う場合は extras を追加
pip install 'noctivault[local-enc]'
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

## Encrypted Local Store（.yaml.enc）

暗号化ファイル `noctivault.local-store.yaml.enc` を優先して利用できます（仕様は docs/api.md を参照）。典型的な運用:

- 初回セットアップ
  - `pip install 'noctivault[local-enc]'`
  - 平文 `noctivault.local-store.yaml` を編集（VCS には含めない）
  - `noctivault key gen` で鍵ファイルを作成（既定: `~/.config/noctivault/local.key`）
  - `noctivault local seal .` で `.yaml.enc` を生成→こちらをコミット
- 実行時
  - `.yaml.enc` があれば自動的に優先され、内部で復号→既存フローでロード
  - 追加設定が必要な場合は `NoctivaultSettings.local_enc` で鍵/パスフレーズ入力方法を指定

## Status

MVP / Draft。`source: local` のみ実装（remote は予約）。仕様は docs/api.md を正とします。

<!-- Dev helper commands intentionally omitted (no Makefile). -->

## License

See LICENSE.
