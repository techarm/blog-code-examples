// rusoto_credential 0.47 の AutoRefreshingProvider が
// 「取得失敗(Err)を永久キャッシュし、二度と再取得しない」ことの再現。
// 実 AWS には一切接続しない。内側のプロバイダの戻り値だけで挙動を確かめる。
//
// シナリオ（本番インシデントに忠実）:
//   1回目      … 成功（クレデンシャル取得）。しばらく正常に動く
//   リフレッシュ … 有効期限が切れて再取得 → 失敗（ローテーション更新の一時失敗）
//   3回目以降   … もう復旧して成功するはず … なのに二度と呼ばれない
//
// ポイント: AutoRefreshingProvider が内側を呼ぶのは「キャッシュが None のとき」だけ。
//   None になるのは (1) 起動直後 (2) 成功キャッシュが期限切れになった直後 の2回のみ。
//   期限切れ後のリフレッシュが失敗すると Some(Err) で固定され、復帰経路が無い。

use async_trait::async_trait;
use chrono::{Duration as ChronoDuration, Utc};
use rusoto_credential::{
    AutoRefreshingProvider, AwsCredentials, CredentialsError, ProvideAwsCredentials,
};
use std::sync::atomic::{AtomicUsize, Ordering};
use std::time::Duration;

struct RotatingProvider {
    calls: AtomicUsize,
}

#[async_trait]
impl ProvideAwsCredentials for RotatingProvider {
    async fn credentials(&self) -> Result<AwsCredentials, CredentialsError> {
        let n = self.calls.fetch_add(1, Ordering::SeqCst);
        match n {
            // 1回目: 成功。有効期限は「今から21秒後」。
            // rusoto は残り20秒を切ると期限切れ扱い（expires_at < now + 20s）なので、
            // 21秒先はバッファの1秒外。発行直後の attempt 1 ではまだ有効（=OK）になる。
            // その後 main 側の sleep(2s) で残りが約19秒になり、attempt 2 で期限切れ扱い → リフレッシュ。
            0 => {
                println!("  [inner] call #{n} -> Ok (有効期限 +21s)");
                Ok(AwsCredentials::new(
                    "AKIAEXAMPLE",
                    "secret",
                    None,
                    Some(Utc::now() + ChronoDuration::seconds(21)),
                ))
            }
            // 2回目（期限切れ後のリフレッシュ）: 失敗
            1 => {
                println!("  [inner] call #{n} -> Err (リフレッシュ失敗)");
                Err(CredentialsError::new("refresh failed"))
            }
            // 3回目以降: 成功（もう復旧している）… が、ここには到達しない
            _ => {
                println!("  [inner] call #{n} -> Ok (復旧済み)");
                Ok(AwsCredentials::new(
                    "AKIAEXAMPLE",
                    "secret",
                    None,
                    Some(Utc::now() + ChronoDuration::hours(1)),
                ))
            }
        }
    }
}

#[tokio::main]
async fn main() {
    let provider =
        AutoRefreshingProvider::new(RotatingProvider { calls: AtomicUsize::new(0) }).unwrap();

    for attempt in 1..=5 {
        match provider.credentials().await {
            Ok(_) => println!("attempt {attempt}: OK"),
            Err(e) => println!("attempt {attempt}: ERR ({e})"),
        }
        // 有効期限の20秒バッファを跨いでリフレッシュを発生させるために少し待つ
        tokio::time::sleep(Duration::from_secs(2)).await;
    }

    println!("\ncall #2（復旧済みの成功）は一度も呼ばれない。");
    println!("一度キャッシュした Err から戻る経路が無く、再起動するまで poison が続く。");
}
