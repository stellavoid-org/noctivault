# Noctivault — API Reference (Draft)

Version: 0.1.0 (MVP)
Status: Draft — settings/client split. Implemented `source=local` and `source=remote` (GCP). Encrypted local store (`.yaml.enc`) supported.

---

## Overview

Noctivault loads secrets from cloud Secret Managers into process memory without going through environment variables. Configuration is separated from execution.

- Settings: `NoctivaultSettings` — pure configuration model
- Client: `noctivault(settings=...)` or `Noctivault(settings=...)` — the loader

Supported modes:

- `source: "local"` — load from local YAML (`noctivault.local-store.yaml`)
- `local encrypted` — prefer `noctivault.local-store.yaml.enc`; decrypt internally, then validate and resolve
- `source: "remote"` — fetch from GCP Secret Manager (ADC only)

Values are wrapped as masked types (`pydantic.SecretStr` via `SecretValue`), so `repr/str` prints `***` by default.

---

## Spec Snapshot

- GCP: fetch by `gcp_project_id`, `ref` (secret name), `version` (int or `latest`)
- Declarative mapping: `{ platform, gcp_project_id, ref, version, cast }`
- Access patterns: `secrets.database.password` or `secrets["database"]["password"]`
- Security: masked by default; `to_dict(reveal=True)` expands real values
- Non‑functional: cache/TTL/force‑refresh (future), detailed errors, local fallback

---

## Install

```bash
pip install noctivault
# Encrypted local store
pip install 'noctivault[local-enc]'
# Remote (GCP)
pip install 'noctivault[gcp]'
```

Depends on `pydantic>=2`.

---

## Quickstart

Create settings:

```python
from noctivault import NoctivaultSettings

settings = NoctivaultSettings(source="local")  # or "remote"
```

Initialize client and load:

```python
import noctivault

nv = noctivault.noctivault(settings=settings)
secrets = nv.load()  # -> SecretNode (nested mapping, masked)

print(secrets.database.password)       # -> ***
real = secrets.database.password.get() # get real value explicitly
```

---

## Concepts

### Settings vs Client

- NoctivaultSettings: configuration only
- Noctivault client: resolves secrets based on `source`

### Sources

- Local: reads `noctivault.local-store.yaml` (prefers `.yaml.enc`)
- Remote: reads `noctivault.yaml` references and fetches from GCP Secret Manager (ADC)

### Secret Tree

Resolution returns a nested tree. Traverse by attribute or key. Leaves are masked `SecretValue` objects; use `.get()` for the real value.

---

## File Format — Local Mocks

Filename: `noctivault.local-store.yaml` (encrypted: `noctivault.local-store.yaml.enc`)

Schema:

```yaml
platform: google              # required
gcp_project_id: my-proj       # required
secret-mocks:                 # required list
  - platform: google          # optional; inherits top-level if omitted
    gcp_project_id: my-proj   # optional; inherits top-level if omitted
    name: <string>            # required, e.g., "db-password"
    value: <string>           # required (stored as string)
    version: 4                # required (int)
```

Notes

- Local store mocks remote values; top-level `platform` and `gcp_project_id` are required, entry fields override when provided.
- Values are stored as strings.

---

## Local Store Encryption (NVLE1)

Encrypt the plaintext mocks file to `noctivault.local-store.yaml.enc`. At runtime, `.enc` takes precedence and is decrypted internally before schema validation and resolution.

Highlights

- Preference: `.yaml.enc` > `.yaml`
- Cipher: AES‑256‑GCM (AEAD); tamper → decryption failure
- KDF (passphrase mode): Argon2id with parameters in the header
- Keying: key‑file and passphrase modes; key‑file is default
- Extras: `cryptography`, `argon2-cffi` via `noctivault[local-enc]`

Header/format

- Magic: `NVLE1`
- Fields: nonce (12B), ciphertext, tag
- Passphrase header: `MAGIC` + `MODE(0x01)` + `KDF_ID(0x01=argon2id)` + params + salt + nonce + ciphertext
- Binary encoding (ASCII armor may be added in the future)

Key material

- Key‑file: 256‑bit random; default `~/.config/noctivault/local.key` (0600)
- Passphrase: derive via Argon2id; interactive prompts supported in CLI

Settings (snippet)

```python
class NoctivaultSettings(BaseModel):
    source: str = "local"
    local_enc: LocalEncSettings | None = None

class LocalEncSettings(BaseModel):
    mode: Literal["key-file", "passphrase"] = "key-file"
    key_file_path: str | None = None
    passphrase: str | None = None
```

Resolution (local)

- Prefer `.yaml.enc`; decrypt to YAML text
- Validate with `TopLevelConfig`, resolve with `SecretResolver`
- Key/passphrase precedence:
  - Key: `settings.local_enc.key_file_path` → `NOCTIVAULT_LOCAL_KEY_FILE` → `./local.key` → `~/.config/noctivault/local.key`
  - Passphrase: `settings.local_enc.passphrase` → `NOCTIVAULT_LOCAL_PASSPHRASE`
- Errors: `InvalidEncHeaderError`, `DecryptError`, `MissingKeyMaterialError`

CLI

- `noctivault key gen [--out <path>]`
- `noctivault local seal <dir|file> [--key-file <path> | --passphrase <pw> | --prompt] [--out <path>] [--rm-plain] [--force]`
- `noctivault local unseal <enc_file> [--key-file <path> | --passphrase <pw> | --prompt]`
- `noctivault local verify <enc_file> [--key-file <path> | --passphrase <pw> | --prompt]`

Operational guidance

- Exclude plaintext `.yaml` from VCS (`.gitignore`)
- Commit/distribute `.yaml.enc`; deliver keys via a secure channel
- Treat decryption failures as immediate errors

---

## File Format — Reference

Filename: `noctivault.yaml` (plaintext)

Schema

```yaml
platform: google              # required
gcp_project_id: my-proj       # required
secret-refs:
  - cast: my-var              # required (leaf key)
    ref: <secret-name>        # required (Secret Manager identifier)
    version: latest | <int>   # optional (default: latest)
    type: str | int           # optional (default: str)

  - key: my-group             # optional (intermediate group key)
    children:
      - cast: my-python-var   # resolves to my-group.my-python-var
        ref: <secret-name>
        version: latest | <int>
        type: str | int
```

Notes

- Top‑level `platform` and `gcp_project_id` are required and inherited by entries/children when omitted
- Google only for now; AWS/Azure fields are not supported
- `type` per leaf: allowed values `str|int` (default `str`)

---

## Resolution Flow

Local

- File selection: prefer `.yaml.enc`, otherwise `.yaml`
- For each ref, look up `(platform, gcp_project_id, name=ref, version)` in mocks
  - If `version=latest` (or omitted), choose the highest integer version available
  - Missing entries raise `MissingLocalMockError`
- Cast per `type` (`str` or `int`), raising `TypeCastError` on failure
- Place as masked `SecretValue` at the final path derived from `key/children` and `cast`
- Duplicate final paths raise `DuplicatePathError`

Remote (GCP)

- Read references from `noctivault.yaml`; ignore mocks entirely
- Auth: ADC only (`GOOGLE_APPLICATION_CREDENTIALS` or workload identity)
- Minimal retries inside the provider (no user config):
  - 404: short single retry (~0.2s)
  - 5xx: short exponential backoff, up to 3 tries (0.2s/0.4s/0.8s)
  - 429: use gRPC RetryInfo if present; otherwise 1.0s/2.0s/4.0s (max 3)
- Decode: bytes → UTF‑8; failure raises `RemoteDecodeError`
- Error mapping: NotFound→`MissingRemoteSecretError`; PermissionDenied/Unauthenticated→`AuthorizationError`; InvalidArgument→`RemoteArgumentError`; DeadlineExceeded/ServiceUnavailable→`RemoteUnavailableError`; others→`DecryptError`

---

## Python API

### `class NoctivaultSettings`

Signature

```python
NoctivaultSettings(
    source: str = "local",
)
```

Parameters

- `source`: which source to use (`local` or `remote`)

Note: remote‑specific settings (auth paths, retry/timeout) are not exposed; use ADC. Cloud identifiers live in the declarative files (top‑level/entries).

### Provider Abstraction

`SecretResolver` consumes a provider with `fetch(platform, project, name, version) -> str`.
Local: `LocalMocksProvider`. Remote: `GcpSecretManagerProvider`.

### Errors (remote)

- `MissingRemoteSecretError` — not found
- `AuthorizationError` — auth/permission issues
- `RemoteArgumentError` — invalid request
- `RemoteUnavailableError` — transient unavailability/timeout
- `RemoteDecodeError` — payload is not valid UTF‑8

---

### `def noctivault(settings: NoctivaultSettings) -> Noctivault`

Factory function creating a client from settings.

### `class Noctivault`

Methods

- `load(local_store_path: str = "../") -> SecretNode`
  Load secrets and return a masked tree. For `source=="local"`, `local_store_path` behaves like `load_dotenv("../")`: if a directory is given, prefer `noctivault.local-store.yaml.enc`, otherwise use `noctivault.local-store.yaml`; if a file is given, use it. Decrypt `.enc`, validate, then resolve. For `source=="remote"`, read `noctivault.yaml` (the `local_store_path` directory) and fetch from GCP.

- `get(path: str) -> Any` (optional)
  Return the real value for dot‑path `"a.b.c"` (raises `KeyError` if missing). Return type follows `type` (default `str`).

- `display_hash(path: str) -> str` (optional)
  Hash of the pre‑cast raw string: `sha3_256(utf8(raw)).hexdigest()`. Independent of `type`. Raises `KeyError` when missing.

---

### `class SecretNode`

- Traverse by attribute or key
- Leaves hold `SecretStr`; call `.get()` to reveal
- `equals(candidate: str) -> bool` (optional) — casts according to `type` then compares; raises `TypeCastError` if cast fails
- `to_dict(reveal=False)` masks; `reveal=True` expands real values (handle with care)

Example

```python
secrets.database.password          # attribute access
secrets["database"]["password"]    # key access
secrets.database.password.get()    # -> str
secrets.database.password.equals("s3cr3t")  # -> bool
secrets.to_dict()                  # masked
```

---

## Errors

- `MissingLocalMockError`: ref missing in local mocks
- `ValidationError`: schema validation failed (e.g., non‑int version)
- `TypeCastError`: failed to cast to requested `type`
- `DuplicatePathError`: multiple refs target the same final path
- `FileNotFoundError`: local store file not found
- `KeyError` / `AttributeError`: path not found
- Remote errors: see above (`MissingRemoteSecretError`, `AuthorizationError`, `RemoteArgumentError`, `RemoteUnavailableError`, `RemoteDecodeError`)

---

## Security & Logging

- Masked by default (`repr/str` prints `***`)
- Minimize `.get()` calls before sending to logs/LLMs
- Avoid `to_dict(reveal=True)` except for tests/tools
- `display_hash` is non‑reversible; for sensitive comparisons consider salting or HMAC (e.g., HMAC‑SHA3‑256)

---

## Testing

- Place `noctivault.local-store.yaml` as test fixture
- Use `to_dict()` (masked) for snapshots
- Use `display_hash(path)` to compare values without revealing them

---

## Input Rules

- Duplicate final paths are not allowed (`DuplicatePathError`)
- Identifiers: `key` and `cast` should match `[A-Za-z_][A-Za-z0-9_]*`; dot `.` is reserved for path separators
- Versions: integers only; `latest` resolves to the highest integer version
- Mocks: `name`, `value`, `version` required; entries inherit `platform`/`gcp_project_id` from top level when omitted
- Refs: top‑level `platform`/`gcp_project_id` required; each entry requires `ref` and `cast` (or via `key/children`); `type` in `{str,int}`
  Refs’ platform/project must match mocks’ effective values in local mode.

---

## License

MIT — see `LICENSE`.

## Changelog

See GitHub Releases.

