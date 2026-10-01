#!/usr/bin/env python3
"""Snakeで、Layaが壁や自分の体にぶつかる方向（blocked）を選ぶか。

ぶつかる方向が必ず1つ以上ある局面を、実際のプレイから集める。
指示に "Never choose blocked." を入れるかどうか、ぶつかる方向をどう書くかで、
blocked を選ぶ割合と、林檎に近づく方向を選ぶ割合がどう変わるかを見る。

    python blocked_check.py --n 120
"""

from __future__ import annotations

import argparse
import random

import snake_core as sc

BASE = "Which direction should the snake move next? Read `directions`. "
TOWARD = "Choose the direction that is toward the apple."

VARIANTS = {
    "避けろと書かない": ("blocked", BASE + TOWARD),
    "Never choose blocked. と書く": ("blocked", BASE + "Never choose blocked. " + TOWARD),
    "ぶつかる方向を deadly と書く": ("deadly", BASE + TOWARD),
    "ぶつかる方向を無関係な語 stone と書く": ("stone", BASE + TOWARD),
}


def collect(n: int) -> list[dict]:
    cases = []
    rng = random.Random(0)
    seed = 0
    while len(cases) < n and seed < 4000:
        seed += 1
        g = sc.Snake(seed=seed)
        for _ in range(300):
            safe = g.safe_options()
            if not safe:
                break
            fatal = [d for d in g.options() if g.fatal(d)]
            if fatal:
                hr, hc = g.head()
                ar, ac = g.apple
                closer = [
                    d for d in safe
                    if abs(g.cell_after(d)[0] - ar) + abs(g.cell_after(d)[1] - ac)
                    < abs(hr - ar) + abs(hc - ac)
                ]
                cases.append({
                    "dirs": dict(sc.build_state(g)["directions"]),
                    "crit": sc.build_criteria(g),
                    "fatal": set(fatal),
                    "closer": set(closer),
                })
                if len(cases) >= n:
                    break
            g.step(rng.choice(safe))
            if not g.alive:
                break
    return cases


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=120)
    ap.add_argument("--backend", default="mlx", choices=["mlx", "torch"])
    args = ap.parse_args()

    if args.backend == "mlx":
        import laya_mlx as laya
    else:
        import laya
    agent = laya.load("convaiinnovations/laya", subfolder="multilingual")

    cases = collect(args.n)
    print(f"ぶつかる方向が必ずある局面 {len(cases)} 件\n")
    for label, (word, instr) in VARIANTS.items():
        bad = hit = opp = 0
        for c in cases:
            d = {k: (word if v == "blocked" else v) for k, v in c["dirs"].items()}
            r = agent.predict({"directions": d},
                              {"q": {"type": "choice", "instructions": instr, "criteria": c["crit"]}})
            pick = r["answers"]["q"]["choice"]
            bad += pick in c["fatal"]
            if c["closer"]:
                opp += 1
                hit += pick in c["closer"]
        print(f"  {label:34} ぶつかる方向 {bad:3}/{len(cases)}（{bad / len(cases) * 100:4.1f}%）  "
              f"林檎に近づく方向 {hit}/{opp}（{hit / max(opp, 1) * 100:5.1f}%）")


if __name__ == "__main__":
    main()
