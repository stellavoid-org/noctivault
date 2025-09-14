# Noctivault — API Reference (Draft)

> Version: 0.1.0 (MVP)
> Status: Draft — **`settings` と `client` を分離**。`source` は `local` と `remote(GCP)` を実装。暗号化ローカルストア（`.yaml.enc`）を実装済み。

---

## Overview

Noctivault は、クラウドの Secret Manager から **環境変数を経由せず** にシークレットをプロセス内メモリへ安全に読み込む Python ライブラリです。設計上、設定と実行を分離します。

* **Settings**: `NoctivaultSettings` — 設定オブジェクト（実行ロジックは持たない）
* **Client**: `noctivault(settings=...)` または `Noctivault(settings=...)` — ローダー本体

サポート状態:

* `source: "local"` — ローカル YAML (`noctivault.local-store.yaml`) からロード。
* `local encrypted` — 暗号化 YAML（`noctivault.local-store.yaml.enc`）を優先してロードし、内部で復号後に既存フローで解決。
* `source: "remote"` — GCP Secret Manager（ADC のみ）から取得。AWS/Azure は未サポート。

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
> Encrypted local store: `pip install 'noctivault[local-enc]'`（`cryptography`, `argon2-cffi`）。

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

* `local`: カレントディレクトリの `noctivault.local-store.yaml` を読み込み（`.yaml.enc` を優先）。
* `remote`: `noctivault.yaml` の参照定義を読み込み、GCP Secret Manager から取得（ADC のみ）。

### Secret Tree

ロード結果は **ネスト木構造**。属性/キーで辿れ、葉はマスク表示される秘密値（`SecretValue` 内部で `SecretStr` を保持）として表現される。`repr/str` は `***` にマスク、実値は `.get()` でのみ露出。

---

## File Format — Local Mocks

**Filename**: `noctivault.local-store.yaml`（暗号化時は `noctivault.local-store.yaml.enc`）

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

## Local Store Encryption（仕様・設計）

平文の `noctivault.local-store.yaml` を暗号化して `noctivault.local-store.yaml.enc` として配布可能にします。ランタイムは `.enc` を優先して読み、内部で復号後に既存のスキーマ検証と解決フローを実行します。

要点

- 優先順位: `.yaml.enc` が存在すればそれを使用。無ければ従来の `.yaml` を使用。
- 暗号方式: AES-256-GCM（AEAD）。改ざん時は復号失敗。
- KDF（passphrase モード時）: Argon2id（必須）。パラメータ（time/memory/parallelism）をヘッダに格納。
- 鍵配布: 2モード併用（key-file / passphrase）。デフォルトは key-file。
- 依存パッケージ（extras）: `cryptography`, `argon2-cffi`（`pip install 'noctivault[local-enc]'`）。

暗号化ファイル仕様（NVLE1）

- ヘッダマジック: `NVLE1`
- fields:
  - algo: `AES-256-GCM`
  - nonce: 12 bytes（ランダム）
  - ciphertext: UTF-8 の YAML 平文を暗号化した本体
  - tag: GCM 認証タグ
  - passphrase モード時のヘッダ構成:
    - `MAGIC` + `MODE (0x01)` + `KDF_ID` + `params` + `salt` + `nonce` + `ciphertext`
    - `KDF_ID`: `0x01=argon2id`
    - `params`（argon2id）: `time_cost(1) | parallelism(1) | memory_cost(4)`（big-endian）
    - `salt`: `salt_len(1)` の直後に続く可変長
- エンコード: バイナリ（将来的に ASCII armor をオプション追加可）。

鍵の扱い

- key-file モード（推奨・非対話運用に適）：
  - 256-bit ランダム鍵（生成コマンドで作成）。
  - 既定配置: `~/.config/noctivault/local.key`（権限 600）。
  - ランタイムは設定から鍵ファイルを参照、復号に使用。
- passphrase モード（人間フレンドリ）：
  - 対話でパスフレーズを取得し、Argon2id で鍵導出。
  - ランタイムはフック/プロンプトでパスフレーズを受け取り復号。

設定（実装）

```python
class NoctivaultSettings(BaseModel):
    source: str = "local"
    # 暗号化ローカルストア向け設定（任意）
    local_enc: LocalEncSettings | None = None

class LocalEncSettings(BaseModel):
    mode: Literal["key-file", "passphrase"] = "key-file"
    key_file_path: str | None = None         # default: ~/.config/noctivault/local.key
    passphrase: str | None = None            # 実運用では secure input を推奨（テスト便宜用）
```

解決フロー（`source==local` の場合）

- パス解決時に `.yaml.enc` を優先探索。存在すれば復号して YAML テキストを得る。
- 復号成功後は従来どおり `TopLevelConfig` で検証し、`SecretResolver` で解決。
- 鍵/パスフレーズ解決の優先順位:
  - Key file: `settings.local_enc.key_file_path` → `NOCTIVAULT_LOCAL_KEY_FILE` → 同ディレクトリの `local.key` → `~/.config/noctivault/local.key`
  - Passphrase: `settings.local_enc.passphrase` → `NOCTIVAULT_LOCAL_PASSPHRASE`
- エラー種別（例）:
  - `InvalidEncHeaderError`（ヘッダ不正）
  - `DecryptError`（鍵不一致/タグ検証失敗）
  - `MissingKeyMaterialError`（鍵未提供）

CLI（事前処理ツール、仕様）

- `noctivault key gen [--out <path>]` — 256-bit 鍵を生成（権限600）。出力パス未指定時は `~/.config/noctivault/local.key`。
- `noctivault local seal <dir|file> [--key-file <path> | --passphrase <pw> | --prompt] [--out <path>] [--rm-plain] [--force]`
  - ディレクトリ指定時、直下の `noctivault.local-store.yaml` を入力として `noctivault.local-store.yaml.enc` を出力。
  - `--rm-plain` 指定時は平文を削除（事前に VCS から除外しておくこと）。
  - `--prompt` は passphrase の対話入力。
- `noctivault local unseal <enc_file> [--key-file <path> | --passphrase <pw> | --prompt]` — 復号（標準出力へ）。
- `noctivault local verify <enc_file> [--key-file <path> | --passphrase <pw> | --prompt]` — 復号検証のみ（終了コード/標準出力）。

運用ガイドライン

- 平文 `.yaml` は VCS に含めない（`.gitignore` 推奨）。
- `.yaml.enc` をコミット/配布し、鍵は安全なチャネルで配備（key-file モード推奨）。
- 改ざん検知は GCM タグで担保されるため、復号失敗時は直ちに失敗として扱う。

---

## File Format — Reference

**Filename**: `noctivault.yaml`（平文）

**Schema**

```yaml
platform: google              # required
gcp_project_id: my_proj       # required
secret-refs:
  - cast: my-var                     # required（最終パスの葉キー名）
    ref: <secret-name>               # required（Secret Manager 上の識別子）
    version: latest | <number>       # optional（未指定は latest と等価）
    type: str | int                  # optional（既定は str）。許容値以外はエラー。

  - key: my-group                    # optional（中間ノードのグループ名）
    children:
      - cast: my-python-var          # resolves to my-group.my-python-var
        ref: <secret-name>
        version: latest | <number>
        type: str | int
```

**Notes**

* `platform` と `gcp_project_id` はトップレベルで必須。各エントリ/children では省略可能で、トップレベル値が継承されます。
* 当面は Google のみを対象とします（AWS/Azure フィールドは未サポート）。
* `type` は各 leaf の型指定。許容値は `str` と `int` のみ。未指定は `str` として扱います。

---

## Resolution Flow

source==local の場合の解決フローを明文化します。

- ファイル選択: `.yaml.enc` を優先、無ければ `.yaml`。`.yaml.enc` の場合は復号に成功してから以下を実施。
- secret-refs の各エントリについて、`platform`, `gcp_project_id`, `ref`, `version` をキーとして secret-mocks を検索する。
  - secret-mocks 側の `platform`/`gcp_project_id` はエントリ指定があればそれを、無ければドキュメントのトップレベル値を用いる（effective 値）。refs 側の値と一致するものを対象に検索する。
- `version` が `latest` または未指定なら、secret-mocks 内の同一 `(platform, gcp_project_id, name=ref)` の最大の整数版を選ぶ（この段階ではスキーマ検証済み）。
  - 見つからなければ `MissingLocalMockError`。
- 取得した元文字列（プレキャスト）に `type` 指定（既定は `str`）のキャストを適用する。
  - `type==int` は `int(value)`、`type==str` は `str(value)`。
  - キャストに失敗した場合は `TypeCastError`。
- 得られた値を `SecretStr` に包み、`key/children` と `cast` で決まる最終パスに配置する。
  - 同じ最終パスに複数の定義が到達した場合は `DuplicatePathError`。

source==remote（GCP）の場合は、各 `ref` を GCP Secret Manager に問い合わせて取得します（ADC のみ）。
  - 認証: ADC のみ（`GOOGLE_APPLICATION_CREDENTIALS`、あるいは GCE/GKE/GHA の Workload Identity）
  - タイムアウトやリトライ設定は SDK 既定を使用（外部化しない）
  - デコード: 取得したバイト列は UTF-8 にデコード。失敗時は `RemoteDecodeError`。
  - エラーマッピング: NotFound→`MissingRemoteSecretError`、PermissionDenied/Unauthenticated→`AuthorizationError`、InvalidArgument→`RemoteArgumentError`、DeadlineExceeded/ServiceUnavailable→`RemoteUnavailableError`、その他→`DecryptError`。

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

> `remote` 用の詳細設定（認証パス、リトライ/タイムアウト等）は外部化しません。認証は ADC のみ。クラウド別識別子は **宣言ファイル側**のトップレベル/エントリで指定します。

### Provider Abstraction

`SecretResolver` は `SecretProviderProtocol`（`fetch(platform, project, name, version) -> str`）を受け取ります。local は `LocalMocksProvider`、remote は `GcpSecretManagerProvider` を利用します。

### Errors（remote）

* `MissingRemoteSecretError` — リモートに該当が無い
* `AuthorizationError` — 認可/認証エラー
* `RemoteArgumentError` — 無効な引数
* `RemoteUnavailableError` — 一時的なサービス不可/期限超過
* `RemoteDecodeError` — UTF-8 デコード失敗

---

### `def noctivault(settings: NoctivaultSettings) -> Noctivault`

ファクトリ関数。設定からクライアントを初期化します。

### `class Noctivault`

**Methods**

* `load(local_store_path: str = "../") -> SecretNode`
  シークレットをロードしてマスク付きツリーを返す。`source=="local"` の場合、`local_store_path` は load_dotenv("../") と同じ解釈で処理する（ディレクトリなら直下の `noctivault.local-store.yaml.enc` を優先探索し、無ければ `noctivault.local-store.yaml` を使用。ファイルならそのパスを使用）。該当ファイルを読み（`.enc` は復号）、スキーマ検証を行ってから解決を実施する。

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
* `FileNotFoundError`: `local_store_path` の解決結果として `noctivault.local-store.yaml(.enc)` が見つからない。
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

## License

TBD (MIT or Apache-2.0 suggested)

## Changelog
