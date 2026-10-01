#!/usr/bin/env python3
"""迷路を何本も走らせて、実際の走行での判断の正しさを数える。

diagnose.py は、コードが決まった歩き方で回って集めた分かれ道で正答率を測る。
そこでは Laya multilingual は 98.3% だった。

ところが 31×31 の迷路を1本走らせると、同じ種類の分かれ道（未踏の道と通った道が
混ざっている）8回のうち3回で、Laya は通った道を選んだ。モデル自身が歩いてできる
場面は、診断の場面とは違う。

そこで迷路を何本も走らせ、実際の走行の中での正答率を数える。

    python race_stats.py --seeds 1-20
    python race_stats.py --seeds 1-20 --only laya     # Jev を使わない（APIを叩かない）
"""

from __future__ import annotations

import argparse
import statistics
import time

from maze_core import Maze, forward_moves
import players


def parse_seeds(text: str) -> list[int]:
    out: list[int] = []
    for part in text.split(","):
        if "-" in part:
            a, b = part.split("-")
            out.extend(range(int(a), int(b) + 1))
        else:
            out.append(int(part))
    return out


def run(player, seed: int, size: int, limit: int) -> dict:
    m = Maze(rows=size, cols=size, seed=seed)
    shortest = len(m.shortest_path()) - 1
    asked = mixed = wrong = 0
    t0 = time.perf_counter()
    while not m.at_goal() and len(m.trail) - 1 < limit:
        opts = forward_moves(m)
        unseen = [o for o in opts if not m.visits.get(players._cell(m, o))]
        d = players.step(player, m)
        if d.asked:
            asked += 1
            # 未踏の道と、通ったことのある道が混ざっている分かれ道。
            # 指示では「行ったことがない方を選べ」と言っているので、正解が決まる
            if unseen and len(unseen) < len(opts):
                mixed += 1
                if d.direction not in unseen:
                    wrong += 1
    return {
        "seed": seed,
        "moves": len(m.trail) - 1,
        "shortest": shortest,
        "goal": m.at_goal(),
        "asked": asked,
        "mixed": mixed,
        "wrong": wrong,
        "sec": time.perf_counter() - t0,
    }


def report(name: str, rows: list[dict]) -> None:
    mixed = sum(r["mixed"] for r in rows)
    wrong = sum(r["wrong"] for r in rows)
    goals = sum(r["goal"] for r in rows)
    ratios = [r["moves"] / r["shortest"] for r in rows if r["goal"]]
    perfect = sum(1 for r in rows if r["goal"] and r["moves"] == r["shortest"])
    clean = sum(1 for r in rows if r["wrong"] == 0)
    print(f"\n=== {name}（{len(rows)}本） ===")
    print(f"  ゴール                       : {goals}/{len(rows)}")
    print(f"  未踏と通った道が混ざる分かれ道: {mixed}回 → 通った道を選んだ {wrong}回"
          f"（正答 {(mixed - wrong) / mixed * 100 if mixed else 0:.1f}%）")
    print(f"  通った道を一度も選ばなかった迷路: {clean}/{len(rows)}")
    if ratios:
        print(f"  最短との比 中央値 {statistics.median(ratios):.2f}倍  平均 {statistics.mean(ratios):.2f}倍"
              f"  最短ちょうど {perfect}本")
    print(f"  1本あたりの時間 中央値 {statistics.median(r['sec'] for r in rows):.1f}s")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", default="1-20")
    ap.add_argument("--size", type=int, default=31)
    ap.add_argument("--limit", type=int, default=1500)
    ap.add_argument("--only", choices=["laya", "jev"])
    ap.add_argument("--backend", default="mlx", choices=["mlx", "torch"])
    args = ap.parse_args()

    seeds = parse_seeds(args.seeds)
    who = []
    if args.only != "jev":
        who.append(("Laya multilingual", players.LayaPlayer("multilingual", args.backend)))
    if args.only != "laya":
        who.append(("Jev", players.JevPlayer()))

    results = {}
    for name, p in who:
        rows = []
        for sd in seeds:
            r = run(p, sd, args.size, args.limit)
            rows.append(r)
            print(f"  {name:18} seed {sd:3}  {r['moves']:4}手（最短 {r['shortest']}）"
                  f"  {'ゴール' if r['goal'] else '未到達'}  混在 {r['mixed']:2}回中 {r['wrong']}回外す", flush=True)
        results[name] = rows
        p.close()

    for name, rows in results.items():
        report(name, rows)


if __name__ == "__main__":
    main()
