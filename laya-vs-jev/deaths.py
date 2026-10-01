#!/usr/bin/env python3
"""Snakeで、判断の回数をそろえてJevとLayaを比べる。死に方も分けて数える。

画面で並べると、Layaばかり死んで見える。でもLayaは毎秒50回前後、Jevは毎秒5回前後しか
判断しないので、同じ時間ならLayaは10倍の場面を踏む。死ぬ確率が同じでも、10倍死んで見える。

判断の回数でそろえて数える。死に方は3つに分ける。

    ぶつかる方向を選んだ … モデルが壁や体にぶつかる方向を選び、コードが止めた回数
    詰み                 … どの方向に動いても死ぬ状態になった（自分で閉じ込めた）
    想定外の死           … 安全な方向があったのに死んだ（本来は起きない）

    python deaths.py laya --n 2000
    python deaths.py jev --n 1500      # APIを使う
"""

from __future__ import annotations

import argparse
import time

import snake_core as sc


def play(player, n: int) -> dict:
    seed = 1
    g = sc.Snake(seed=seed)
    out = {"decisions": 0, "apples": 0, "blocked": 0, "trapped": 0, "unexpected": 0}
    for _ in range(n):
        safe = g.safe_options()
        if not safe:
            out["trapped"] += 1
            seed += 1
            g = sc.Snake(seed=seed)
            continue
        pick = player.decide(g).direction
        out["decisions"] += 1
        if g.fatal(pick):
            out["blocked"] += 1
            pick = max(safe, key=g.open_space)
        before = g.score
        g.step(pick)
        out["apples"] += g.score > before
        if not g.alive:
            out["unexpected"] += 1
            seed += 1
            g = sc.Snake(seed=seed)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("who", choices=["laya", "jev"])
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--backend", default="torch", choices=["torch", "mlx"],
                    help="記事の数字は torch（本家）で測った")
    args = ap.parse_args()

    if args.who == "laya":
        from snake import LayaPlayer

        player = LayaPlayer("multilingual", backend=args.backend)
    else:
        from snake import JevPlayer

        player = JevPlayer()

    t0 = time.perf_counter()
    r = play(player, args.n)
    elapsed = time.perf_counter() - t0
    player.close()

    d = max(r["decisions"], 1)
    print(f"{args.who:5} 判断 {r['decisions']:5}  林檎 {r['apples']:4}  "
          f"ぶつかる方向 {r['blocked']:3}（{r['blocked'] / d * 100:.1f}%）  "
          f"詰み {r['trapped']:3}  想定外の死 {r['unexpected']:3}")
    print(f"      1000判断あたり 林檎 {r['apples'] / d * 1000:.1f}  詰み {r['trapped'] / d * 1000:.1f}  "
          f"{r['decisions'] / elapsed:.1f}判断/秒")


if __name__ == "__main__":
    main()
