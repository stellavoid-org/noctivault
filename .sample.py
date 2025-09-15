import hashlib
import tempfile
import textwrap
from pathlib import Path

from noctivault import NoctivaultSettings, noctivault


def main() -> None:
    # サンプル用の YAML を一時ディレクトリに書き出す
    yaml_text = textwrap.dedent(
        """
        platform: google
        gcp_project_id: sample-proj
        secret-mocks:
          - name: x
            value: "00123"
            version: 1
          - name: port
            value: "5432"
            version: 1
        secret-refs:
          - platform: google
            gcp_project_id: sample-proj
            cast: password
            ref: x
            version: 1
            type: str
          - key: database
            children:
              - platform: google
                gcp_project_id: sample-proj
                cast: port
                ref: port
                version: 1
                type: int
        """
    )

    with tempfile.TemporaryDirectory() as tmp:
        cfg_path = Path(tmp) / "noctivault.local-store.yaml"
        cfg_path.write_text(yaml_text, encoding="utf-8")

        # クライアント初期化とロード
        nv = noctivault(NoctivaultSettings(source="local"))
        secrets = nv.load(local_store_path=tmp)

        print("== Masked view ==")
        print(secrets)  # SecretNode(... *** ...)
        print(secrets.to_dict())  # マスクされた dict

        print("\n== Reveal view ==")
        print(secrets.to_dict(reveal=True))  # 実値（型付き）

        print("\n== Accessors ==")
        print("password (masked):", secrets.password)
        print("password (get):", secrets.password.get())
        print("database.port (typed get via client):", nv.get("database.port"))

        print("\n== Hash & Equals ==")
        h = nv.display_hash("password")
        print("display_hash(password):", h)
        print("equals(password, '00123'):", secrets.password.equals("00123"))
        print("equals(database.port, '5432'):", secrets.database.port.equals("5432"))

        # 検証: display_hash はプレキャスト文字列のハッシュ
        assert h == hashlib.sha3_256("00123".encode("utf-8")).hexdigest()


if __name__ == "__main__":
    main()
