# Jev と Laya を比べる

## 記事

[LayaはJevの代わりになるか。速さの対価は質問文の設計だった](https://techarm.dev/posts/laya-vs-jev-prompt-design)

TypeSafe の **Jev**（API）と、オープンソースの **Laya**（手元で動く）に、同じ判断をさせて比べたコードです。
題材は迷路とSnake、それに前の記事と同じ問い合わせ16組です。

記事の数字は 2026年10月1日に、Mac Studio（M1 Ultra / 64GB）で測りました。

## 準備

```bash
uv venv --python 3.12 .venv
VIRTUAL_ENV=.venv uv pip install -r requirements.txt
export TYPESAFE_API_KEY=あなたのキー   # Jev を使うスクリプトだけ必要
```

- Laya の重み（600〜800MB）は、初回の読み込みで `~/.cache/huggingface` に自動で落ちます。2回目からは `HF_HUB_OFFLINE=1` でネットを切っても動きます
- `laya-mlx`（非公式のMLX移植）は Apple Silicon 専用です。それ以外では `--backend torch` を使ってください
- Python 3.14 だと依存パッケージがそろわないことがあるので、3.12 の環境を切っています

| パッケージ | 版 |
|---|---|
| laya（本家） | 0.3.22 |
| laya-mlx（非公式） | 0.2.0 |
| typesafe-sdk | 0.7.2（モデルは `jev-1.13.0`） |
| pygame | 2.6.1 |
| Pillow | 12.3.0（動画にまとめるときだけ） |

## 記事の数字を再現する

| スクリプト | 何を測るか | 記事の数字 |
|---|---|---|
| `diagnose.py` | 迷路の「まだ行っていない道が1本だけ」の分かれ道60件で、正しく選ぶか | Laya multilingual 98.3% / Jev 100% |
| `race_stats.py` | 迷路を20本走らせて、実際の走行の中で数える | Laya 47.6% / Jev 100% |
| `diagnose_snake.py` | Snakeで、材料の言い回しを変えて林檎に近づく方向を選ぶか（80件） | 12.5% 〜 100% |
| `blocked_check.py` | Snakeで、ぶつかる方向を選ぶか（120件） | `Never choose blocked.` で 0.0%、無しで 5.0% |
| `pocket.py` | Snakeで、`Never choose trap.` を足す前と後 | ぶつかる方向 Jev 0.0%→2.3%、Laya 0.4%→2.2% |
| `deaths.py` | Snakeで、判断の回数をそろえて比べる | 林檎 Jev 61.5 / Laya 39.5（1000判断あたり） |
| `mlx_check.py` | MLX版が本家と同じ答えを返すか（200件） | 200/200 一致、確率の差は最大 0.0027 |
| `lang_compare.py` | 前の記事と同じ16組で、英日の答えがそろうか | Laya 7〜12/16 / Jev 14〜16/16 |

```bash
python diagnose.py --n 60 --jev
python race_stats.py --seeds 1-20 --size 31
python race_stats.py --seeds 1-20 --size 31 --only laya   # Jev を使わない
python diagnose_snake.py --n 80 --jev
python blocked_check.py --n 120
python pocket.py laya --n 2000
python pocket.py jev --n 1000
python deaths.py laya --n 2000
python deaths.py jev --n 1500
python mlx_check.py --n 200
python lang_compare.py --jev
```

`lang_compare.py` は、前の記事のコード（`../typesafe-jev/lang_check.py`）から問い合わせ16組と質問を直接読み込みます。

Jev の答えは、走らせるたびに少し変わることがあります（迷路の最初の分かれ道が 0.5 対 0.5 になるなど）。Laya は毎回同じ答えを返します。

## 並べて走らせるアプリ

```bash
python race.py                      # 迷路。31×31、左上の S から右下の G へ
python snake.py                     # Snake
python race.py --mock               # API もモデルも使わず、見た目だけ確かめる
python snake.py --shot out.png --shot-after 20   # 画面を出さずに画像を書き出す
python snake.py --backend torch     # Laya を本家（PyTorch）で動かす。既定は MLX版
```

記事の動画は、走り終わってから同じ手数ずつ（1コマ4手）描き直したものです。
実際の時間のままだと、Layaは1秒かからずにゴールしてしまい、どう歩いたかが見えないためです。

```bash
python race.py --replay frames                  # 走らせて、1コマずつPNGで書き出す（画面は出さない）
python frames_to_webp.py frames race.webp --fps 12
python race.py --record frames                  # こちらは実時間のまま撮る
```

Jevの手数は走るたびに変わります（2026年10月4日に8回走らせて、328手・384手・432手）。記事の動画は384手の回です。

迷路の画面で、Laya側に出る赤い丸は「まだ行っていない道があるのに、もう通った道を選んだ分かれ道」、
赤い線は「そこから同じ分かれ道に戻ってくるまでの遠回り」です。

## ファイル

| ファイル | 中身 |
|---|---|
| `maze_core.py` | 迷路の生成 |
| `players.py` | 迷路で Jev と Laya に同じ材料・同じ質問を渡す層 |
| `snake_core.py` | Snakeの盤面と、モデルに渡す材料・質問 |
| `ui.py` | 2つのアプリで共有する見た目（色・フォント・部品） |
| `frames_to_webp.py` | `race.py --replay` / `--record` で書き出したPNGを、アニメーションWebPにまとめる |

材料と質問文の書き方は、実測して決めました。なぜその書き方にしたかは、各ファイルのコメントに書いてあります。

## ライセンス

MIT
