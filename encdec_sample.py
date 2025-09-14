# from cryptography.hazmat.primitives.asymmetric import rsa, padding
# from cryptography.hazmat.primitives import hashes

# # 鍵ペア生成
# private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
# public_key = private_key.public_key()

# # 暗号化するテキスト（UTF-8に変換）
# message = "秘密のメッセージ".encode("utf-8")

# # 公開鍵で暗号化
# ciphertext = public_key.encrypt(
#     message,
#     padding.OAEP(
#         mgf=padding.MGF1(algorithm=hashes.SHA256()),
#         algorithm=hashes.SHA256(),
#         label=None
#     )
# )

# # 秘密鍵で復号化
# plaintext = private_key.decrypt(
#     ciphertext,
#     padding.OAEP(
#         mgf=padding.MGF1(algorithm=hashes.SHA256()),
#         algorithm=hashes.SHA256(),
#         label=None
#     )
# )

# # 復号したバイト列を文字列に戻す
# print(plaintext.decode("utf-8"))


import time, statistics, string, secrets
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import UnsupportedAlgorithm

from cryptography.hazmat.backends.openssl.backend import backend
import cryptography
print("OpenSSL (used by cryptography):", backend.openssl_version_text())
print("cryptography:", cryptography.__version__)

# 設定
NUM_SAMPLES = 1000
MSG_LEN = 100  # ASCII letters only
KEY_SIZE = 2048  # 3072/4096にしてもOK（その分遅くなります）

def rand_alpha_ascii(n: int) -> bytes:
    alphabet = string.ascii_letters  # A-Za-z
    return ''.join(secrets.choice(alphabet) for _ in range(n)).encode('ascii')

# 鍵ペア生成（計測対象外）
private_key = rsa.generate_private_key(public_exponent=65537, key_size=KEY_SIZE)
public_key = private_key.public_key()

algos = [
    ("SHA-256", hashes.SHA256()),
    ("SHA3-256", hashes.SHA3_256()),
]

def bench_algo(name, alg):
    enc_times = []
    dec_times = []
    for _ in range(NUM_SAMPLES):
        msg = rand_alpha_ascii(MSG_LEN)
        try:
            t0 = time.perf_counter()
            ct = public_key.encrypt(
                msg,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=alg),
                    algorithm=alg,
                    label=None
                )
            )
            t1 = time.perf_counter()

            t2 = time.perf_counter()
            pt = private_key.decrypt(
                ct,
                padding.OAEP(
                    mgf=padding.MGF1(algorithm=alg),
                    algorithm=alg,
                    label=None
                )
            )
            t3 = time.perf_counter()
        except UnsupportedAlgorithm:
            return {"unsupported": True}

        if pt != msg:
            raise RuntimeError(f"Decryption mismatch for {name}")

        enc_times.append((t1 - t0) * 1000.0)  # ms
        dec_times.append((t3 - t2) * 1000.0)  # ms

    return {
        "unsupported": False,
        "enc_min": min(enc_times), "enc_max": max(enc_times), "enc_avg": statistics.mean(enc_times),
        "dec_min": min(dec_times), "dec_max": max(dec_times), "dec_avg": statistics.mean(dec_times),
    }

print(f"Benchmark: RSA-OAEP on {MSG_LEN} ASCII chars, {NUM_SAMPLES} samples, RSA {KEY_SIZE}-bit")
for name, alg in algos:
    res = bench_algo(name, alg)
    if res.get("unsupported"):
        print(f"[{name}] SKIPPED: OAEP with {name} not supported by this OpenSSL/cryptography backend.")
        continue
    fmt = lambda x: f"{x:,.3f} ms"
    print(f"[{name}]")
    print(f"  encrypt: min {fmt(res['enc_min'])} | max {fmt(res['enc_max'])} | avg {fmt(res['enc_avg'])}")
    print(f"  decrypt: min {fmt(res['dec_min'])} | max {fmt(res['dec_max'])} | avg {fmt(res['dec_avg'])}")
