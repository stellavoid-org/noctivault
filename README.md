# noctivault

[![PyPI](https://img.shields.io/pypi/v/noctivault.svg)](https://pypi.org/project/noctivault/)
[![Python Versions](https://img.shields.io/pypi/pyversions/noctivault.svg)](https://pypi.org/project/noctivault/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Wheel](https://img.shields.io/pypi/wheel/noctivault.svg)](https://pypi.org/project/noctivault/)

Noctivault loads secrets from cloud Secret Managers into process memory without going through environment variables. Values are masked by default, and configuration is clearly separated from execution.

- Safe by default: in‑memory resolution, masked string representations
- Operational clarity: two files — references (refs) and mock values (mocks)
- Flexible: local encrypted store and remote (GCP) fetch supported

## Why Noctivault

- Avoids env‑vars; secrets are handled via explicit API calls
- Lighter than Vault/SOPS for Python apps; DX focused
- Two‑file split clarifies “what to use” (refs) vs “where values come from” (mocks)
- Commit `.yaml.enc`, distribute the key separately for safer, reproducible setups

## Support & Requirements

- Python: >= 3.10
- Local encrypted store: extra `local-enc` (`cryptography`, `argon2-cffi`)
- Remote (GCP): `google-cloud-secret-manager` (also available as extra `gcp`)
- Remote platform support: Google only for now (AWS/Azure on roadmap)

## Install

- pip:
  - `pip install noctivault`
  - Local encrypted store: `pip install 'noctivault[local-enc]'`
  - GCP remote: `pip install google-cloud-secret-manager` (or `pip install 'noctivault[gcp]'`)
- Poetry:
  - `poetry add noctivault`
  - Local encrypted store: `poetry add "noctivault[local-enc]"`
  - GCP remote: `poetry add google-cloud-secret-manager` (or `poetry add "noctivault[gcp]"`)

## Quickstart (Local, two‑file layout)

1) Mocks (plaintext or encrypted source): `noctivault.local-store.yaml`

```yaml
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

2) Refs (plaintext; do not encrypt): `noctivault.yaml`

```yaml
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

3) Encrypt mocks (recommended)

- Generate key: `noctivault key gen` (default `~/.config/noctivault/local.key`, chmod 600)
- Create encrypted file: `noctivault local seal . --key-file ~/.config/noctivault/local.key --rm-plain`
  - Commit `.yaml.enc`; keep plaintext `.yaml` and `local.key` out of VCS

4) Load (Python)

```python
from noctivault import NoctivaultSettings
import noctivault

nv = noctivault.noctivault(settings=NoctivaultSettings(source="local"))
secrets = nv.load(local_store_path="./")  # prefers .enc; falls back to .yaml

print(secrets.database.password)        # -> ***
print(secrets.database.password.get())  # -> "s3cr3t"
print(secrets.database.port.get())      # -> 5432
```

Restore plaintext from `.enc` when needed:

```bash
noctivault local unseal noctivault.local-store.yaml.enc --key-file ~/.config/noctivault/local.key > noctivault.local-store.yaml
```

## Quickstart (Remote, GCP)

Prereqs

- Dependency: `poetry add google-cloud-secret-manager` (or `poetry add "noctivault[gcp]"`)
- Auth (ADC)
  - Service account JSON: `export GOOGLE_APPLICATION_CREDENTIALS=/path/to/sa.json`
  - Or: `gcloud auth application-default login`
- Permission: `roles/secretmanager.secretAccessor`, etc.

`noctivault.yaml` (refs only)

```yaml
platform: google
gcp_project_id: my-gcp-project

secret-refs:
  - key: database
    children:
      - cast: password
        ref: db-password
        version: latest
        type: str
```

Load (Python)

```python
from noctivault import NoctivaultSettings
import noctivault

nv = noctivault.noctivault(settings=NoctivaultSettings(source="remote"))
secrets = nv.load(local_store_path=".")  # reads ./noctivault.yaml
print(secrets.database.password)         # -> ***
print(secrets.database.password.get())   # -> UTF-8 string from GCP
```

Common errors and fixes

- MissingDependencyError: add `google-cloud-secret-manager`
- AuthorizationError: fix ADC/permissions
- MissingRemoteSecretError: check project/ref/version in `noctivault.yaml`

## CLI

- Key: `noctivault key gen [--out PATH]`
- Seal: `noctivault local seal <dir|file> (--key-file PATH | --passphrase PW | --prompt) [--out PATH] [--rm-plain] [--force]`
- Unseal: `noctivault local unseal <enc_file> (--key-file PATH | --passphrase PW | --prompt)`
- Verify: `noctivault local verify <enc_file> (--key-file PATH | --passphrase PW | --prompt)`

When a directory is given, `.yaml.enc` is preferred; otherwise falls back to `.yaml`. You can pass file paths directly as well.

## Settings & Precedence

- `NoctivaultSettings(source="local"|"remote")`
- Local encrypted store key material (in this order):
  - `settings.local_enc.key_file_path`
  - `NOCTIVAULT_LOCAL_KEY_FILE`
  - `./local.key` next to `.enc`
  - `~/.config/noctivault/local.key`
- Passphrase mode
  - `settings.local_enc.passphrase` or `NOCTIVAULT_LOCAL_PASSPHRASE`, or CLI `--prompt`

## Schema Summary

- Mocks (`noctivault.local-store.yaml`)
  - Top‑level `platform`, `gcp_project_id` are required; entries inherit if omitted
  - `secret-mocks`: `name`, `value` (str), `version` (int)
- Refs (`noctivault.yaml`)
  - Top‑level `platform`, `gcp_project_id` required
  - `secret-refs`: entries or grouped by `key`/`children`
  - `type`: `str|int` (default `str`), `version`: `latest|int`

See `docs/api.md` for full details.

## Security

- Masked by default (`repr/str` -> `***`); call `.get()` to reveal
- Encryption format (NVLE1)
  - AES‑256‑GCM; Argon2id (for passphrase); KDF params stored in header
  - Tamper detection via GCM tag; invalid tag -> decryption failure
- Operational guidance
  - Keep plaintext `.yaml` and `local.key` out of VCS (use `.gitignore`)
  - Key files should be mode 600; distribute via secure channels

## Troubleshooting

- CombinedConfigNotAllowedError: don’t mix mocks and refs in one file
- MissingLocalMockError / MissingRemoteSecretError: name/version/project mismatch
- TypeCastError: e.g., `type=int` for non‑numeric values
- InvalidEncHeaderError / DecryptError: bad header / wrong key
- RemoteUnavailableError: transient GCP issues; retry later

## FAQ

- Why two files?
  - Separate intent (refs) from value sources (mocks); simpler reviews and switching between local/remote
- Which file is preferred?
  - Local: `.yaml.enc` > `.yaml`; Remote uses `noctivault.yaml` only
- How to migrate from a single file?
  - Move `secret-mocks` into `noctivault.local-store.yaml`, and `secret-refs` into `noctivault.yaml`

## Roadmap

- Remote drivers for AWS/Azure
- Cache/TTL/force‑refresh
- Pluggable providers; HMAC option for `display_hash`

## Contributing

- PRs welcome. Please keep Ruff/Mypy clean and maintain high test coverage
- For security reports, please use responsible disclosure

## License

MIT — see `LICENSE`.
