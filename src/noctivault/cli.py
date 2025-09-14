from __future__ import annotations

import os
import secrets
import stat
from pathlib import Path
from typing import List, Optional, Union

from noctivault.core.errors import DecryptError, InvalidEncHeaderError
from noctivault.io.enc import (
    seal_with_key,
    seal_with_passphrase,
    unseal_with_key,
    unseal_with_passphrase,
)
from noctivault.io.fs import (
    DEFAULT_LOCAL_STORE_ENC_FILENAME,
    DEFAULT_LOCAL_STORE_FILENAME,
)


def _default_key_path() -> Path:
    return Path.home() / ".config" / "noctivault" / "local.key"


def key_gen(out: Optional[Union[str, Path]] = None) -> str:
    out_path = Path(out) if out is not None else _default_key_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    key = secrets.token_bytes(32)
    out_path.write_bytes(key)
    try:
        os.chmod(out_path, stat.S_IRUSR | stat.S_IWUSR)  # 0o600
    except Exception:
        # On non-POSIX, chmod may not apply as expected; ignore.
        pass
    return str(out_path)


def _resolve_plain_path(base: Union[str, Path]) -> Path:
    p = Path(base)
    if p.is_dir():
        plain = p / DEFAULT_LOCAL_STORE_FILENAME
        if not plain.exists():
            raise FileNotFoundError(f"{plain} not found")
        return plain
    if p.is_file():
        if p.name != DEFAULT_LOCAL_STORE_FILENAME:
            raise FileNotFoundError(f"Unsupported file name: {p.name}")
        return p
    raise FileNotFoundError(str(p))


def seal(
    base: Union[str, Path],
    *,
    key_file_path: Optional[Union[str, Path]] = None,
    passphrase: Optional[str] = None,
    out: Optional[Union[str, Path]] = None,
    rm_plain: bool = False,
    force: bool = False,
) -> str:
    plain_path = _resolve_plain_path(base)
    directory = plain_path.parent
    out_path = Path(out) if out is not None else (directory / DEFAULT_LOCAL_STORE_ENC_FILENAME)
    if out_path.exists() and not force:
        raise FileExistsError(str(out_path))
    pt = plain_path.read_bytes()
    if passphrase is not None and key_file_path is not None:
        raise ValueError("specify either --key-file or --passphrase, not both")
    if passphrase is not None:
        enc = seal_with_passphrase(pt, passphrase)
    else:
        if key_file_path is None:
            raise ValueError("--key-file or --passphrase is required")
        key = Path(key_file_path).read_bytes()
        enc = seal_with_key(pt, key)
    out_path.write_bytes(enc)
    if rm_plain:
        try:
            plain_path.unlink()
        except FileNotFoundError:
            pass
    return str(out_path)


def unseal(
    enc_path: Union[str, Path],
    *,
    key_file_path: Optional[Union[str, Path]] = None,
    passphrase: Optional[str] = None,
) -> bytes:
    data = Path(enc_path).read_bytes()
    if passphrase is not None and key_file_path is not None:
        raise ValueError("specify either --key-file or --passphrase, not both")
    if passphrase is not None:
        return unseal_with_passphrase(data, passphrase)
    if key_file_path is None:
        raise ValueError("--key-file or --passphrase is required")
    key = Path(key_file_path).read_bytes()
    return unseal_with_key(data, key)


def verify(
    enc_path: Union[str, Path],
    *,
    key_file_path: Optional[Union[str, Path]] = None,
    passphrase: Optional[str] = None,
) -> bool:
    try:
        _ = unseal(enc_path, key_file_path=key_file_path, passphrase=passphrase)
        return True
    except (InvalidEncHeaderError, DecryptError):
        return False


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entrypoint for encryption helpers.

    Subcommands:
      - key gen [--out PATH]
      - local seal <path> --key-file PATH [--out PATH] [--rm-plain] [--force]
      - local unseal <enc_path> --key-file PATH
      - local verify <enc_path> --key-file PATH
    """
    import argparse

    parser = argparse.ArgumentParser(prog="noctivault")
    sub = parser.add_subparsers(dest="cmd", required=True)

    # key group
    p_key = sub.add_parser("key")
    sub_key = p_key.add_subparsers(dest="key_cmd", required=True)
    p_key_gen = sub_key.add_parser("gen")
    p_key_gen.add_argument("--out", type=str, default=None)

    # local group
    p_local = sub.add_parser("local")
    sub_local = p_local.add_subparsers(dest="local_cmd", required=True)

    p_seal = sub_local.add_parser("seal")
    p_seal.add_argument("path", type=str)
    group = p_seal.add_mutually_exclusive_group(required=True)
    group.add_argument("--key-file", default=None)
    group.add_argument("--passphrase", default=None)
    p_seal.add_argument("--out", default=None)
    p_seal.add_argument("--rm-plain", action="store_true")
    p_seal.add_argument("--force", action="store_true")
    p_seal.add_argument("--prompt", action="store_true")

    p_unseal = sub_local.add_parser("unseal")
    p_unseal.add_argument("enc_path", type=str)
    group_u = p_unseal.add_mutually_exclusive_group(required=False)
    group_u.add_argument("--key-file", default=None)
    group_u.add_argument("--passphrase", default=None)
    p_unseal.add_argument("--prompt", action="store_true")

    p_verify = sub_local.add_parser("verify")
    p_verify.add_argument("enc_path", type=str)
    group_v = p_verify.add_mutually_exclusive_group(required=False)
    group_v.add_argument("--key-file", default=None)
    group_v.add_argument("--passphrase", default=None)
    p_verify.add_argument("--prompt", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "key" and args.key_cmd == "gen":
        path = key_gen(args.out)
        print(path)
        return 0

    if args.cmd == "local":
        if args.local_cmd == "seal":
            pw = args.passphrase
            if args.prompt and pw is None:
                import getpass

                pw = getpass.getpass("Passphrase: ")
            out_path = seal(
                args.path,
                key_file_path=args.key_file,
                passphrase=pw,
                out=args.out,
                rm_plain=args.rm_plain,
                force=args.force,
            )
            print(out_path)
            return 0
        if args.local_cmd == "unseal":
            pw = args.passphrase
            if args.prompt and pw is None:
                import getpass

                pw = getpass.getpass("Passphrase: ")
            data = unseal(args.enc_path, key_file_path=args.key_file, passphrase=pw)
            print(data.decode("utf-8"), end="")
            return 0
        if args.local_cmd == "verify":
            pw = args.passphrase
            if args.prompt and pw is None:
                import getpass

                pw = getpass.getpass("Passphrase: ")
            ok = verify(args.enc_path, key_file_path=args.key_file, passphrase=pw)
            print("OK" if ok else "FAIL")
            return 0 if ok else 1

    parser.print_help()
    return 2
