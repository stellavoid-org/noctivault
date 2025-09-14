# Noctivault — Architecture (MVP)

この文書は docs/api.md（正本）を補完し、実装レイヤー・依存関係・データフローを固定するための設計メモです。対象は MVP（source==local）で、remote は拡張ポイントとして明示に留めます。

## Scope & Principles

- 正本は docs/api.md。スキーマ/挙動はそちらに準拠。
- 既定でマスク、露出は明示（.get()）。暗黙の文字列化は禁止。
- パス制約: `key`/`cast` は `[A-Za-z_][A-Za-z0-9_]*`、ドットは区切り専用。
- トップレベル（YAML最上位）で `platform`, `gcp_project_id` 必須。mocks エントリは未指定ならトップレベルを継承（オーバーライド可）。

## Layering

1) Core Domain
- SecretValue: pydantic.SecretStr を内包。表示マスク、get()、equals(candidate: str) の責務を切り出し。
- SecretNode: ネスト木。属性/キーアクセス、to_dict(reveal=False)、葉へ equals デリゲート。
- Path: ドットパスの正規化・検証（APIの制約に一致）。
- Errors: MissingLocalMockError, DuplicatePathError などドメイン例外。

2) Schema & Validation
- Models: トップレベル、secret-refs、secret-mocks の Pydantic モデル群。
- Normalization: トップレベル継承（platform/gcp_project_id）の反映、`version` 型検証（整数 or "latest"）、`type` の許容値検証（"str"/"int"、未指定は"str"）。
- 事前検証でスキーマ/型のみを担保。パス衝突は後段 Resolver が検出。

3) Source Providers (Port/Adapter)
- SecretsProvider (Protocol): `fetch(ref, version) -> str`。
- LocalMocksProvider: mocks をインデックス化し、`(platform, project, name, version)` から値を返す。`latest` は最大整数版を選択。
- RemoteProvider: 予約（NotImplemented）。将来 GCP/AWS/Azure 実装を差し替え可能に。

4) Resolver (Application Service)
- SecretResolver: refs を順に解決し、選択値を TreeBuilder に流す。
- VersionResolver: `latest` の具象化（最大整数版）。
- ValueCaster: 取得した元文字列（プレキャスト）に `type` 指定を適用（`str`/`int`）。失敗時は `TypeCastError`。
- ConflictDetector: 最終パス衝突時に DuplicatePathError。

5) Tree & Assembly
- TreeBuilder: `key/children + cast` で決まる最終パスに値を配置。葉は SecretValue にラップ。
- NodeFactory: dict から SecretNode を生成。

6) Client API
- Noctivault: 設定保持。`load(local_store_path="../") -> SecretNode`、`get(path) -> str`、`display_hash(path) -> str` を提供。
- Factory: `noctivault(settings) -> Noctivault`。
- 備考: 葉ノードには `equals(candidate: str) -> bool` を提供（SecretNode セクション参照）。
  - get(path): `type` 指定に従う（`int`なら int、省略は str）。
  - display_hash(path): 常にプレキャストの元文字列をハッシュ。
  - equals(candidate): `type` 規則で candidate をキャストして比較。失敗は `TypeCastError`。

7) IO & Parsing
- PathResolver: load_dotenv("../") 同等の解釈（ディレクトリ→`noctivault.local-store.yaml`、ファイル→そのまま）。
- YamlReader: UTF-8 で読み込み、エラーを明確化。

8) Logging & Policy
- Redaction: repr/str は常に `***`。例外/ログに SecretValue/SecretNode を流してもマスクされる。
- Context reveal は採用しない（露出は .get() のみ）。

## Data Flow (source==local)

1. Client.load(local_store_path)
2. IO.fs でファイルパス解決 → IO.yaml で読み込み
3. Schema.validate でスキーマ検証・正規化（トップレベル継承、version 型）
4. Provider.local_mocks が mocks をインデックス化
5. Resolver が refs を順に解決（`latest`→最大整数版選択）
6. TreeBuilder が最終パスへ SecretValue を配置（衝突検出）
7. NodeFactory が SecretNode を返す

## Error Strategy

- FileNotFoundError: local_store_path の解決先が見つからない。
- ValidationError: スキーマ検証失敗（型、必須不足、`version` 非整数など）。
- TypeCastError: `type` 指定に従った値のキャストに失敗。
- MissingLocalMockError: refs の参照が mocks に存在しない。
- DuplicatePathError: 同一の最終パスに複数定義が到達。
- ValueError("Unknown source: ..."): 未サポート source。
- NotImplementedError: source==remote（MVP）。

## Package Layout (proposal)

```
noctivault/
  core/
    value.py        # SecretValue
    node.py         # SecretNode
    path.py         # Path rules
    errors.py
  schema/
    models.py       # Top-level, refs, mocks
    validate.py
  provider/
    base.py         # SecretsProvider
    local_mocks.py
    remote_gcp.py   # stub
  app/
    resolver.py     # SecretResolver, VersionResolver, ConflictDetector
    tree.py         # TreeBuilder, NodeFactory
  io/
    fs.py           # PathResolver
    yaml.py         # YamlReader
  client.py         # Noctivault, noctivault()
```

## Testing Strategy

- schema: トップレベル継承、`latest`、不正 `version` 等の単体。
- provider: インデックス化、`latest` 選択、見つからないケース。
- resolver+tree: パス衝突、深いパス構築、SecretValue ラップ。
- client: load 経路、`get`/`display_hash`、葉の `equals`。

## Future (Remote)

- Provider を差し替えるだけで Resolver/Tree は再利用可能な設計とする。
- 認証/タイムアウト/リトライは RemoteProvider 配下に閉じ込め、API からは透過化。
