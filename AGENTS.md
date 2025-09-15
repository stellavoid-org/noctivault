# DPS Interaction Gateway - Project Guidelines

### 型安全性（Strict型安全プロファイル）
**mypy strict = true 完全準拠済み:**

```python
# ✅ すべての関数に型アノテーション必須
async def create_session(guild_id: GuildId, user_id: UserId) -> Session:
    ...

# ✅ Protocolで依存性の境界を定義
class RepositoryProtocol(Protocol):
    async def save(self, entity: T) -> None: ...

# ✅ テストでautospec使用（spec_set=True必須）
mock = create_autospec(Service, instance=True, spec_set=True)

# ⚠️ cast()は最小限・理由コメント必須
guild_id = cast(GuildId, headers.get('X-Guild-Id'))  # 外部入力のため型変換
```

## エラー修正方針
- CRITICAL : 場当たり的な対応をせず、全体を俯瞰してベストな方法で修正する。ハードコードを減らし、安全な方法で実装する。必要なら設計の見直しから提案し、無理な修正をする前に立ち止まる。
- CRITICAL : エラー修正時や実装時は、毎回、必要なファイルを読んだか立ち止まる。わかった気になっているだけで間違えている。今回の実装を検討する。できなければできないと認め、停止する。
- あなたに時間の都合はない。どんなに時間がかかっても読めと言われたファイルをすべて読め。やるべき実装を慎重にしろ。急ぐな。
-   実装前チェックリスト（必須）：
```
  □ スケルトンの該当部分を読んだか？（存在する場合。行番号まで特定）
  □ その処理フローを説明できるか？
  □ なぜそう実装されているか理解したか？
  □ specの該当部分を確認したか？（存在する場合。行番号まで特定）
```