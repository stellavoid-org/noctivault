import secrets

import pytest


def test_seal_unseal_roundtrip_with_key():
    from noctivault.io.enc import seal_with_key, unseal_with_key

    key = secrets.token_bytes(32)
    pt = b"hello world"
    enc = seal_with_key(pt, key)
    out = unseal_with_key(enc, key)
    assert out == pt


def test_unseal_invalid_header_raises():
    from noctivault.core.errors import InvalidEncHeaderError
    from noctivault.io.enc import unseal_with_key

    key = secrets.token_bytes(32)
    with pytest.raises(InvalidEncHeaderError):
        unseal_with_key(b"BAD!" + b"\x00" * 32, key)


def test_unseal_wrong_key_raises():
    from noctivault.core.errors import DecryptError
    from noctivault.io.enc import seal_with_key, unseal_with_key

    k1 = secrets.token_bytes(32)
    k2 = secrets.token_bytes(32)
    enc = seal_with_key(b"data", k1)
    with pytest.raises(DecryptError):
        unseal_with_key(enc, k2)


def test_seal_unseal_with_passphrase_roundtrip():
    from noctivault.io.enc import seal_with_passphrase, unseal_with_passphrase

    pt = b"hello secret"
    enc = seal_with_passphrase(pt, "hunter2")
    out = unseal_with_passphrase(enc, "hunter2")
    assert out == pt


def test_unseal_with_passphrase_wrong_raises():
    from noctivault.core.errors import DecryptError
    from noctivault.io.enc import seal_with_passphrase, unseal_with_passphrase

    enc = seal_with_passphrase(b"data", "right")
    with pytest.raises(DecryptError):
        unseal_with_passphrase(enc, "wrong")


def test_passphrase_header_includes_kdf_id():
    from noctivault.io.enc import KDF_ID_ARGON2ID, MAGIC, MODE_PASSPHRASE, seal_with_passphrase

    data = seal_with_passphrase(b"x", "pw")
    assert data.startswith(MAGIC)
    assert data[len(MAGIC)] == MODE_PASSPHRASE
    kdf_id = data[len(MAGIC) + 1]
    assert kdf_id == KDF_ID_ARGON2ID
