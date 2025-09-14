# Noctivault — API Reference (Draft)

> Version: 0.1.0 (MVP)
> Status: Draft — **`settings` と `client` を分離**。`source` は `local` を実装、`remote` は予約。

---

## Overview

Noctivault は、クラウドの Secret Manager から **環境変数を経由せず** にシークレットをプロセス内メモリへ安全に読み込む Python ライブラリです。設計上、設定と実行を分離します。

* **Settings**: `NoctivaultSettings` — 設定オブジェクト（実行ロジックは持たない）
* **Client**: `noctivault(settings=...)` または `Noctivault(settings=...)` — ローダー本体

サポート状態:

* `source: "local"` — ローカル YAML (`noctivault.local-store.yaml`) からロード。
* `source: "remote"` — Secret Manager バックエンド（GCP/AWS/Azure）用。*v0.2.0では未実装*。

値は `pydantic.SecretStr` などにキャストされ、`repr/str` は `***` にマスクされます。

---

## Spec Snapshot（要件からの抜粋）

* GCP Secret Manager を対象に `gcp_project_id`, `secret_name(ref)`, `version` 指定で取得（remote 実装時）。
* 宣言的マッピング: { `platform`, `gcp_project_id`, `ref`, `version`, `field`, `cast` }。
* 動的アクセス: `secrets.database.password` または `secrets["database"]["password"]`。
* セキュリティ: 既定でマスク、`.to_dict(reveal=True)` でのみ生値展開。
* 非機能: 永続/TTL キャッシュ、強制再フェッチ、詳細なエラー、`noctivault.local-store.yaml` へのフォールバック（local）。

---

## Install

```bash
pip install noctivault  # (package name TBD)
```

> Depends on `pydantic>=2`.

---

## Quickstart

**1) 設定を作る**

```python
from noctivault import NoctivaultSettings

settings = NoctivaultSettings(
    source="local",  # or "remote" (reserved)
)
```

**2) クライアントを初期化してロード**

```python
import noctivault

nv = noctivault.noctivault(settings=settings)  # or Noctivault(settings)
secrets = nv.load()  # -> SecretNode（ネスト辞書 + マスク表示）

print(secrets.database.password)          # -> SecretNode(***), masked
real = secrets.database.password.get()    # 明示的に実値を取得
```

---

## Concepts

### Settings vs Client

* **NoctivaultSettings**: 構成のみを保持する純粋なデータモデル。
* **Noctivault Client**: Settings を受け取り、`source` に応じて適切なローダーでシークレットを読み込む。

### Source

* `local`: カレントディレクトリの `noctivault.local-store.yaml` を読み込み。
* `remote`: 将来的に GCP/AWS/Azure の Secret Manager から取得（未実装）。

### Secret Tree

ロード結果は **ネスト木構造**。属性/キーで辿れ、葉は `SecretStr` にラップされる。`repr/str` はマスク、実値は `.get()` でのみ露出。

---

## File Format — Local Source

**Filename**: `noctivault.local-store.yaml`

**Schema**:

```yaml
platform: google              # required
gcp_project_id: my_proj       # required
secret-mocks:                 # required, list of mock entries
  - platform: google          # optional — remote のモックとして扱う。なければrequiredの方を使用する。
    gcp_project_id: my-proj   # optional — remote と同一の識別に必須。なければrequiredの方を使用する。
    name: <string>            # required, e.g., "db-password"
    value: <string>           # required, secret value (string)
    version: 4                # required (非数値はエラー)
  - platform: google
    gcp_project_id: my-proj
    name: <string>
    value: <string>
    version: 7
```

**Notes**

* Local store は「remote の値ストアのモック」。`platform` と `gcp_project_id` はトップレベルで必須、エントリでは任意（指定時はトップレベル値をオーバーライド）。
* 値は文字列で受け取り `SecretStr` として保持されます。

---

## File Format — Local/Remote Reference

**Filename**: `noctivault.reference.yaml`

**Schema**

```yaml
platform: google              # required
gcp_project_id: my_proj       # required
secret-refs:
  - platform: google                 # required（local でも必須）
    gcp_project_id: <string>         # required（local でも必須）
    cast: my-var                     # required（最終パスの葉キー名）
    ref: <secret-name>               # required（Secret Manager 上の識別子）
    version: latest | <number>       # optional（未指定は latest と等価）
    type: str | int                  # optional（既定は str）。許容値以外はエラー。

  - key: my-group                    # optional（中間ノードのグループ名）
    children:
      - platform: google
        gcp_project_id: <string>
        cast: my-python-var          # resolves to my-group.my-python-var
        ref: <secret-name>
        version: latest | <number>
        type: str | int              # optional（既定は str）。許容値以外はエラー。
```

**Notes**

* Local/Remote で **同一スキーマ** を使用します。`source==local` でも `platform` と `gcp_project_id` は必須です（remote のモックとして解決するため）。
* 当面は Google のみを対象とします（AWS/Azure フィールドは未サポート）。
* `type` は各 leaf の型指定。許容値は `str` と `int` のみ。未指定は `str` として扱います。

---

## Resolution Flow

source==local の場合の解決フローを明文化します。

- secret-refs の各エントリについて、`platform`, `gcp_project_id`, `ref`, `version` をキーとして secret-mocks を検索する。
  - secret-mocks 側の `platform`/`gcp_project_id` はエントリ指定があればそれを、無ければドキュメントのトップレベル値を用いる（effective 値）。refs 側の値と一致するものを対象に検索する。
- `version` が `latest` または未指定なら、secret-mocks 内の同一 `(platform, gcp_project_id, name=ref)` の最大の整数版を選ぶ（この段階ではスキーマ検証済み）。
  - 見つからなければ `MissingLocalMockError`。
- 取得した元文字列（プレキャスト）に `type` 指定（既定は `str`）のキャストを適用する。
  - `type==int` は `int(value)`、`type==str` は `str(value)`。
  - キャストに失敗した場合は `TypeCastError`。
- 得られた値を `SecretStr` に包み、`key/children` と `cast` で決まる最終パスに配置する。
  - 同じ最終パスに複数の定義が到達した場合は `DuplicatePathError`。

source==remote の場合は、各 `ref` をクラウド Secret Manager に問い合わせて取得する（未来実装）。

---

## Python API

### `class NoctivaultSettings`

**Signature**

```python
NoctivaultSettings(
    source: str = "local",
)
```

**Parameters**

* `source`: 使用するソースを指定。

> `remote` 用のフィールド（例: 認証/タイムアウト/キャッシュ設定など）は将来追加します。クラウド別識別子は **宣言ファイル側**（YAML/JSON/Dict の各エントリ）で指定します。

---

### `def noctivault(settings: NoctivaultSettings) -> Noctivault`

ファクトリ関数。設定からクライアントを初期化します。

### `class Noctivault`

**Methods**

* `load(local_store_path: str = "../") -> SecretNode`
  シークレットをロードしてマスク付きツリーを返す。`source=="local"` の場合、`local_store_path` は load_dotenv("../") と同じ解釈で処理する（ディレクトリなら直下の `noctivault.local-store.yaml` を探索、ファイルならそのパスを使用）。該当ファイルが存在すればスキーマ検証を行ってから解決を実施する。

* `get(path: str) -> Any` *(optional)*
  `"a.b.c"` のドットパスで即座に実値を取得（存在しない場合は `KeyError`）。返す値の型は `type` 指定に従う（既定は `str`）。

* `display_hash(path: str) -> str` *(optional)*
  get() のハッシュ版。プレキャストの元文字列を UTF-8 でエンコードし、`hashlib.sha3_256(data).hexdigest()` を返す（`type` に依らず元文字列が同じなら同一ハッシュ）。存在しないパスは `KeyError`。

> 実装メモ: v0.2.0 では `local` のみ。`remote` 実装時に GCP/AWS/Azure ドライバを内部登録する想定。

---

### `class SecretNode`

* 属性/キーアクセスでネストを辿れる。
* 葉ノードは `SecretStr` を保持し、`.get()` で実値。
* `equals(candidate: str) -> bool` *(optional)* — `type` 指定に従って候補をキャストしてから等価比較を返す（True/False）。キャスト不能は `TypeCastError`。完全一致のみ。正規化やトリムは行わない。
* `to_dict(reveal=False)` はマスク、`reveal=True` で実値展開（取扱注意）。

```python
secrets.database.password          # attribute access
secrets["database"]["password"]    # key access
secrets.database.password.get()    # -> str
secrets.database.password.equals("s3cr3t")  # -> bool
secrets.to_dict()                  # masked
```

---

## Errors

* `MissingLocalMockError`: `source==local` で `secret-refs` の参照が `secret-mocks` に見つからない。
* `ValidationError`（または同等のスキーマ検証エラー）: `noctivault.local-store.yaml` の検証に失敗（例: `version` が整数でない、必須フィールド欠落）。
* `TypeCastError`: `type` 指定に従った値のキャストに失敗（例: `type=int` で非数値）。
* `DuplicatePathError`: `secret-refs` の解決結果が同じ最終パスに衝突した。
* `FileNotFoundError`: `local_store_path` の解決結果として `noctivault.local-store.yaml` が見つからない。
* `KeyError` / `AttributeError`: 存在しないパス参照。
* `ValueError("Unknown source: ...")`: 未サポートの `source`。
* `NotImplementedError`: `source==remote`（v0.1.0）。

> 将来の `remote` では、ネットワーク/認可（IAM）/整合性エラー等をサーフェスします。

---

## Security & Logging

* 既定でマスク（`repr/str` は `***`）。
* LLM や外部ログへ渡す前に `.get()` 呼び出しを最小化する設計を推奨。
* `to_dict(reveal=True)` はテスト/運用ツール以外では使用を避ける。
* `display_hash` は非可逆だが同値判定には使える。衝突耐性は高いものの機密比較に用いる場合はソルトや HMAC（例: HMAC-SHA3-256 with app secret）の利用を検討。

---

## Testing

* `noctivault.local-store.yaml` をテストフィクスチャとして配置。
* スナップショットには `to_dict()`（マスク済）を利用。
* 安定した同一性確認が必要な場合は `display_hash(path)` を活用（生値の露出を避けつつ比較可能）。

---

## Input Rules

入力の制約と一意性のルールを定義します。

- パスの重複: 同一の最終パスに複数の定義が到達した場合は `DuplicatePathError`。
- 文字種: `key` および `cast` は `[A-Za-z_][A-Za-z0-9_]*` を推奨。ドット `.` はパス区切り専用で、`key`/`cast` 自体には使用不可。
- version: 整数のみ許可。`latest` は secret-mocks 内の最大整数版を指す。
- secret-mocks: `name`, `value`, `version` は必須。`platform` と `gcp_project_id` はエントリ未指定ならドキュメントのトップレベルから継承。両方とも不在の場合はスキーマエラー。
- secret-refs: `platform`, `gcp_project_id`, `ref`, `cast`（または `key/children` 経由での `cast`）は必須。`version` 未指定は `latest` と同等に解決。`type` は `str` または `int` のみ（未指定は `str`）。
  refs の `platform`/`gcp_project_id` と、mocks の effective 値は一致していなければならない。`type=int` 指定時のキャスト失敗は `TypeCastError`。

---

## Minimal Reference Implementation (Sketch)

以下は概念スケッチです（正確なコードではありません）。

```python
# 1) settings
class NoctivaultSettings(BaseModel):
    source: Literal["local", "remote"] = "local"
    local_store_path: str = "../"  # dir -> join('noctivault.local-store.yaml')

# 2) loader outline
class Noctivault:
    def load(self) -> SecretNode:
        if self.settings.source == "local":
            cfg = read_yaml(resolve_path(self.settings.local_store_path))
            refs = cfg.get("secret-refs", [])
            mocks = cfg.get("secret-mocks", [])
            # トップレベルのデフォルト (platform, gcp_project_id) を考慮してインデックス化
            index = index_mocks_by_platform_project_ref_version(
                mocks,
                defaults=(cfg.get("platform"), cfg.get("gcp_project_id")),
            )
            out = {}
            for ref in flatten_refs(refs):  # yields (platform, project, path_parts, ref_name, version)
                version = resolve_version(index, ref, default_latest=True)
                value = lookup_mock(index, ref.platform, ref.project, ref.ref_name, version)
                if value is None:
                    raise MissingLocalMockError(ref)
                put_value(out, ref.path_parts, SecretStr(value), on_conflict_error=DuplicatePathError)
            return SecretNode(out)
        raise NotImplementedError("remote")
```

---

## License

TBD (MIT or Apache-2.0 suggested)

## Changelog
