#!/usr/bin/env python3
"""Snakeで、袋小路の情報を足すとどうなるか。3つの書き方を同じ条件で比べる。

「打ったあと、蛇の体が入りきらない狭い空間しか残らない方向」に入ると、いつか必ず詰む。
これを材料（state）にどう書くか。

    none        … 書かない（既定。記事の結論）
    trap_word   … その方向を "trap" と書き、指示に "Never choose trap." を足す
    as_blocked  … その方向も "blocked" と書く（新しい語を増やさない）

結果（1000判断あたり。記事に載せた数字）:
    Jev  none 0.0% → trap_word 2.3%   ← ぶつかる方向（blocked）を選ぶ割合
    Laya none 0.4% → trap_word 2.2%
禁止をもう1つ足したら、もとの禁止（Never choose blocked）が守られなくなった。
trap の方向は即死しないので、この割合には入れていない。

    python pocket.py laya --n 2000
    python pocket.py jev --n 1000      # APIを使う
"""

from __future__ import annotations

import argparse
import time

import snake_core as sc

BASE = "Which direction should the snake move next? Read `directions`. Never choose blocked. "
INSTR = {
    "none": BASE + "Choose the direction that is toward the apple.",
    "trap_word": BASE + "Never choose trap. Choose the direction that is toward the apple.",
    "as_blocked": BASE + "Choose the direction that is toward the apple.",
}


def build(g: sc.Snake, mode: str) -> dict:
    hr, hc = g.head()
    ar, ac = g.apple
    out = {}
    for d in g.options():
        if g.fatal(d):
            out[d] = "blocked"
            continue
        r, c = g.cell_after(d)
        closer = abs(r - ar) + abs(c - ac) < abs(hr - ar) + abs(hc - ac)
        plain = "toward the apple" if closer else "away"
        if mode != "none" and sc.is_trap(g, d):
            out[d] = "trap" if mode == "trap_word" else "blocked"
        else:
            out[d] = plain
    return {"directions": out}


def play(ask, mode: str, n: int) -> tuple[int, int, int, int]:
    seed = 1
    g = sc.Snake(seed=seed)
    decisions = apples = blocked = trapped = 0
    for _ in range(n):
        safe = g.safe_options()
        if not safe:  # どう動いても死ぬ＝詰み
            trapped += 1
            seed += 1
            g = sc.Snake(seed=seed)
            continue
        pick = ask(build(g, mode), sc.build_criteria(g), INSTR[mode])
        decisions += 1
        if g.fatal(pick):  # ぶつかる方向を選んだら、コードが止める
            blocked += 1
            pick = max(safe, key=g.open_space)
        before = g.score
        g.step(pick)
        apples += g.score > before
        if not g.alive:
            trapped += 1
            seed += 1
            g = sc.Snake(seed=seed)
    return decisions, apples, blocked, trapped


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("who", choices=["laya", "jev"])
    ap.add_argument("--n", type=int, default=2000)
    ap.add_argument("--backend", default="torch", choices=["torch", "mlx"],
                    help="記事の数字は torch（本家）で測った")
    args = ap.parse_args()

    if args.who == "laya":
        if args.backend == "mlx":
            import laya_mlx as laya
        else:
            import laya
        agent = laya.load("convaiinnovations/laya", subfolder="multilingual")

        def ask(state, crit, instr):
            r = agent.predict(state, {"q": {"type": "choice", "instructions": instr, "criteria": crit}})
            return r["answers"]["q"]["choice"]

        close = lambda: None  # noqa: E731
    else:
        from typesafe_sdk import Choice, TypeSafeClient

        client = TypeSafeClient()

        def ask(state, crit, instr):
            r = client.system_one(
                state=state,
                questions={"q": Choice(instructions={"question": instr, "inspect": "`directions`"},
                                       criteria=crit)},
            )
            return r.answers["q"].choice

        close = client.close

    for mode in ("none", "trap_word", "as_blocked"):
        t0 = time.perf_counter()
        dec, apples, blocked, trapped = play(ask, mode, args.n)
        k = 1000 / max(dec, 1)
        print(f"{args.who:5} {mode:11} 判断 {dec:5}  林檎 {apples * k:5.1f}  詰み {trapped * k:4.1f}  "
              f"ぶつかる方向 {blocked / max(dec, 1) * 100:4.1f}%（1000判断あたり）  "
              f"{dec / (time.perf_counter() - t0):.1f}判断/秒")
    close()


if __name__ == "__main__":
    main()
