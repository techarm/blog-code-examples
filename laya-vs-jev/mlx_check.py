#!/usr/bin/env python3
"""非公式のMLX移植（laya-mlx）が、本家（laya / PyTorch）と同じ答えを返すか。

laya-mlx は Laya を作った人とは別の人が、Apple Silicon 向けにニューラルネットの部分を
MLX で書き直したもの。2026年10月1日の時点で6コミットしかない。速さの前に、
同じ答えを返すかを確かめる。

Snakeの実際の局面を集めて、両方に同じ材料・同じ質問を投げる。

    python mlx_check.py --n 200
"""

from __future__ import annotations

import argparse
import random
import statistics
import time

import snake_core as sc


def collect(n: int) -> list[tuple[dict, dict]]:
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
            cases.append((sc.build_state(g), sc.build_criteria(g)))
            if len(cases) >= n:
                break
            g.step(rng.choice(safe))
            if not g.alive:
                break
    return cases


def run(agent, cases, instr: str):
    lat, out = [], []
    for state, crit in cases:
        t = time.perf_counter()
        r = agent.predict(state, {"q": {"type": "choice", "instructions": instr, "criteria": crit}})
        lat.append((time.perf_counter() - t) * 1000)
        a = r["answers"]["q"]
        out.append((a["choice"], a.get("probabilities", {})))
    return out, lat[5:]  # 最初の数回はウォームアップなので除く


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--checkpoint", default="multilingual")
    args = ap.parse_args()

    import laya
    import laya_mlx

    cases = collect(args.n)
    instr = f"{sc.QUESTION} {sc.FOCUS}"
    print(f"Snakeの実際の局面 {len(cases)} 件\n")

    torch_out, torch_lat = run(laya.load("convaiinnovations/laya", subfolder=args.checkpoint), cases, instr)
    mlx_out, mlx_lat = run(laya_mlx.load("convaiinnovations/laya", subfolder=args.checkpoint), cases, instr)

    for label, lat in (("本家 PyTorch", torch_lat), ("laya-mlx（非公式）", mlx_lat)):
        print(f"{label:20} p50 {statistics.median(lat):6.2f}ms  min {min(lat):6.2f}  max {max(lat):7.2f}")

    same = sum(1 for a, b in zip(torch_out, mlx_out) if a[0] == b[0])
    diffs = [abs(pa[k] - pb[k]) for (_, pa), (_, pb) in zip(torch_out, mlx_out) for k in pa if k in pb]
    print(f"\n答えの一致      : {same}/{len(cases)}")
    print(f"確率の差 中央値 : {statistics.median(diffs):.5f}   最大 {max(diffs):.5f}")


if __name__ == "__main__":
    main()
