# Jevを日本から測る

## 記事

[Jevは日本語で使えるのか。落ちるのは「データ」ではなく「質問文」だった](https://techarm.dev/posts/typesafe-jev-japanese-latency)

TypeSafe AI の **Jev**（System One モデル）を、大阪から実際に叩いて測ったスクリプトを置いています。
Jev は文章を生成しません。状態（`state`）と型のついた質問を渡すと、質問ごとに確率つきの答えが返ってくるだけのモデルです。

| ファイル | 測るもの |
|---|---|
| `bench.py` | レイテンシ。質問1つ vs 3つ同時、state が英語 vs 日本語の4条件 |
| `scale_check.py` | 質問を1個から27個まで増やしたときのレイテンシとトークン |
| `lang_check.py` | 日本語で判定がぶれるか。英語版と日本語版の答えが一致するかを見る |

記事に載せた数字は、`bench.py --n 40` / `scale_check.py --n 15` / `lang_check.py --repeat 2` で
2026年9月19日に大阪から測ったものです。

## 準備

```bash
pip install -r requirements.txt
export TYPESAFE_API_KEY=あなたのキー
```

記事の計測時点の SDK は `typesafe-sdk` 0.7.0、モデルは `jev-1.13.0` です。

APIキーは [TypeSafe](https://typesafe.ai/) の early access で発行されます。

## レイテンシ計測

```bash
python bench.py --n 40
```

測るのは2つです。

1. **質問1つ vs 3つ同時** — 公式の「並列に評価されるので質問を増やしても劣化しない」の検証
2. **state が英語 vs 日本語** — 公式が「CJKは精度が落ちる」と書いている件の確認

2の比較では、質問文と選択肢は英語に固定し、**変えるのは state の言語だけ**にしています。
両方いっぺんに変えると、何が効いたのか分からなくなるためです。

結果は `bench-result.json` に残ります。

> [!NOTE]
> 公式のベンチマークは「西海岸にある自分たちのノートPCから」実行したものだと公式ブログに明記されています。
> 日本から叩いた数字とは別物として見てください。

## 質問数とレイテンシ

```bash
python scale_check.py --n 15
```

質問を 1 → 3 → 9 → 18 → 27 個と増やして、p50 と入力トークンを並べます。
27個というのは公式デモ（`typesafe-race`）と同じ粒度です。あのデモが速いのは
**質問をまとめた条件だから**なので、本当に平らなのかを同じところまで伸ばして確かめます。

## 日本語で判定がぶれるか

```bash
python lang_check.py --repeat 2
python lang_check.py --repeat 2 --jp-questions   # 質問文と選択肢も日本語にする
```

正解ラベルは用意していません。自分のつけたラベルが正しいか、という別の議論になるからです。

代わりに、**同じ内容の問い合わせを英語版と日本語版で16対**つくって、まったく同じ質問を投げ、
**答えが一致するか**を見ます。食い違えば、内容ではなく言語が結果を動かしたことになります。

`--jp-questions` を付けると質問文と選択肢まで日本語になります。
公式ドキュメントが言う「他の言語」が `state` の話なのか質問文の話なのかを切り分けるためのフラグです。

## 公式ドキュメントとの対応

| 公式の指針 | このコードでの対応 |
|---|---|
| state はオブジェクトで渡し、各部分に名前を付ける | `state={"ticket": ...}` `state={"message": ...}` |
| 独立した質問は1回のリクエストにまとめる | Choice / Score / Noul を1回で投げる |
| 質問文と選択肢は英語で書く | `instructions` と `criteria` は英語（`--jp-questions` は検証用の例外） |
| クライアントは context manager で使う | 全スクリプトで `with TypeSafeClient()` |
| APIキーは環境変数から | コード中にキーを書かない |

## 参考

- [Introducing System One Models & Jev](https://typesafe.ai/blog/introducing-system-one-models-and-jev)
- [State](https://docs.typesafe.ai/concepts/state) — 日本語の精度についての記述はここ
- [Models](https://docs.typesafe.ai/models) — 上限値と言語サポート
- [Jev 1.13 jaggedness](https://docs.typesafe.ai/model-jaggedness/jev-1.13) — 公式が挙げている弱点

## ライセンス

MIT
