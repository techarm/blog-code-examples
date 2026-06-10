# 古い AWS SDK のネガティブキャッシュ 最小再現

開発停止済みの `rusoto_credential` 0.47 の `AutoRefreshingProvider` が「取得失敗（`Err`）を永久にキャッシュし、二度と再取得しない」挙動を再現する最小コードです。実 AWS には一切接続しません。

## 記事

[「認証情報が取れない」が再起動でしか直らない ― 古い AWS SDK のネガティブキャッシュ落とし穴](https://techarm.dev/posts/rust-aws-credential-negative-cache)

## 必要条件

- Rust（edition 2024 / cargo）

## 実行方法

```bash
cargo run
```

本番インシデントに忠実なシナリオを再現します。**最初は成功して正常に動くが、有効期限切れ後のリフレッシュが一度失敗した瞬間に poison し、その後エンドポイントが復旧しても認証エラーを返し続ける**（再起動するまで直らない）。

## 期待される出力

```text
  [inner] call #0 -> Ok (有効期限 +21s)
attempt 1: OK
  [inner] call #1 -> Err (リフレッシュ失敗)
attempt 2: ERR (refresh failed)
attempt 3: ERR (refresh failed)
attempt 4: ERR (refresh failed)
attempt 5: ERR (refresh failed)
```

`call #2`（復旧済みの成功）のログが **一度も出ない** のがポイントです。一度キャッシュした `Err` から戻る経路が無いため、内側プロバイダは二度と呼ばれません。

> 実行には数秒かかります（有効期限の 20 秒バッファを跨いでリフレッシュを発生させるため、各試行の間に 2 秒スリープしています）。

## 仕組み

- `AutoRefreshingProvider` が内側プロバイダを呼ぶのは、キャッシュが `None` のときだけ
- `None` になるのは「起動直後」と「成功キャッシュが期限切れになった直後」の 2 回のみ。有効期限内は成功キャッシュをそのまま返す
- 期限切れ後のリフレッシュが失敗すると `Some(Err)` で固定され、`Some(Err)` を `None` に戻す経路が無いため復帰できない
- そのため「3 回目以降は成功するはず」のクレデンシャルには永遠に到達しない

## 確認バージョン

- `rusoto_credential` 0.47.0（OSS, MIT / Apache-2.0）
- 検証日: 2026-06-10
