# Noctivault

Noctivault は、クラウドの Secret Manager から環境変数を介さずにシークレットをプロセス内メモリへ安全に読み込む Python ライブラリです。設定と実行を分離し、値は既定でマスク表示されます。

## Install

```bash
pip install noctivault                 # package name TBD
# 暗号化ローカルストア（.yaml.enc）を使う場合は extras を追加
pip install 'noctivault[local-enc]'
# GCP Remote を使う場合
pip install 'noctivault[gcp]'
```

## Quickstart（2ファイル構成）

1) Mocks（平文 or 暗号化）: `noctivault.local-store.yaml`（例）

```
platform: google
gcp_project_id: demo

secret-mocks:
  - name: db-password
    value: s3cr3t
    version: 2
  - name: db-port
    value: "5432"
    version: 1
```

2) Refs（平文）: `noctivault.yaml`

```
secret-refs:
  - key: database
    children:
      - platform: google
        gcp_project_id: demo
        cast: password
        ref: db-password
        version: latest
        type: str
      - platform: google
        gcp_project_id: demo
        cast: port
        ref: db-port
        version: 1
        type: int
```

3) ロード（Python）

```python
from noctivault import NoctivaultSettings
import noctivault

nv = noctivault.noctivault(settings=NoctivaultSettings(source="local"))
secrets = nv.load(local_store_path="./")  # ディレクトリ指定で .enc を優先, なければ .yaml

print(secrets.database.password)       # -> ***
print(secrets.database.password.get()) # -> s3cr3t
print(secrets.database.port.get())     # -> "5432"
```

YAML スキーマ（mocks/refs・解決フロー・入力制約など）の詳細は docs/api.md を参照してください。

- ドキュメント: docs/api.md

## Quickstart（Remote / GCP）

前提:

- 依存のインストール: `pip install 'noctivault[gcp]'`
- 認証: ADC（`GOOGLE_APPLICATION_CREDENTIALS`、または GCE/GKE/GitHub Actions の Workload Identity）

1) Refs（平文）: `noctivault.yaml`

```
platform: google
gcp_project_id: demo

secret-refs:
  - key: database
    children:
      - cast: password
        ref: db-password
        version: latest
        type: str
      - cast: port
        ref: db-port
        version: 1
        type: int
```

2) ロード（Python）

```python
from noctivault import NoctivaultSettings
import noctivault

nv = noctivault.noctivault(settings=NoctivaultSettings(source="remote"))
secrets = nv.load(local_store_path="./")  # ディレクトリに noctivault.yaml を置く

print(secrets.database.password)       # -> ***
print(secrets.database.password.get()) # -> 実値（GCPから取得）
print(secrets.database.port.get())     # -> "5432"
```

注意:

- Remote は mocks（`noctivault.local-store.yaml(.enc)`）を完全に無視します（refs のみ使用）。
- プラットフォームは現状 Google のみサポート（`platform: google`）。
- SDK のリトライ/タイムアウトは既定値を使用します。

## CLI

`pyproject.toml` のエントリにより `noctivault` コマンドが利用できます。

- 鍵作成: `noctivault key gen`（既定: `~/.config/noctivault/local.key`、権限600）
- 暗号化: `noctivault local seal <dir> --key-file ~/.config/noctivault/local.key`（または `--passphrase`/`--prompt`）
- 復号: `noctivault local unseal <enc> --key-file ...`（または `--passphrase`/`--prompt`）
- 検証: `noctivault local verify <enc> --key-file ...`

環境変数での指定（ランタイム時）

- `NOCTIVAULT_LOCAL_KEY_FILE`（キーファイルパス）
- `NOCTIVAULT_LOCAL_PASSPHRASE`（パスフレーズ）

## .gitignore 推奨

リポジトリには暗号化ファイルのみを含め、平文は除外してください。

```
noctivault.local-store.yaml
local.key
```

## Encrypted Local Store（.yaml.enc）

暗号化ファイル `noctivault.local-store.yaml.enc` を優先して利用できます（仕様は docs/api.md を参照）。KDF は Argon2id を使用します（`pip install 'noctivault[local-enc]'`）。典型的な運用:

- 初回セットアップ
  - `pip install 'noctivault[local-enc]'`
  - 平文 `noctivault.local-store.yaml` を編集（VCS には含めない）
  - `noctivault key gen` で鍵ファイルを作成（既定: `~/.config/noctivault/local.key`）
  - `noctivault local seal .` で `.yaml.enc` を生成→こちらをコミット
- 実行時
  - `.yaml.enc` があれば自動的に優先され、内部で復号→既存フローでロード
  - 追加設定が必要な場合は `NoctivaultSettings.local_enc` で鍵/パスフレーズ入力方法を指定

## Status

MVP / Draft。`source: local` と `source: remote (GCP, ADCのみ)` を実装。仕様は docs/api.md を正とします。

<!-- Dev helper commands intentionally omitted (no Makefile). -->

## License

See LICENSE.
