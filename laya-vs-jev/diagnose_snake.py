#!/usr/bin/env python3
"""Snakeで「りんごに近づく手」を選べるか。実際の局面を集めて測る。

手で作った状態1つで試すと当たるのに、実戦だと当たらないことがあった。
1局面の結果はたまたまなので、**実際のプレイ中に出てくる局面**を集めて数える。

集めるのは「安全な手のうち、りんごに近づくのがちょうど1つ」という局面だけ。
正解が1つに決まるので、当てずっぽうの期待値も計算できる。

使い方:
    python diagnose_snake.py --n 80
    python diagnose_snake.py --n 80 --jev
"""

from __future__ import annotations

import argparse
import random
import time

import snake_core as sc


def collect(n: int) -> list[dict]:
    """安全な手が2つ以上あり、そのうち「近づく手」がちょうど1つの局面。"""
    out: list[dict] = []
    rng = random.Random(0)
    seed = 0
    while len(out) < n and seed < 4000:
        seed += 1
        g = sc.Snake(seed=seed)
        for _ in range(300):
            safe = g.safe_options()
            if not safe:
                break
            hr, hc = g.head()
            ar, ac = g.apple
            closer = []
            for d in safe:
                r, c = g.cell_after(d)
                if abs(r - ar) + abs(c - ac) < abs(hr - ar) + abs(hc - ac):
                    closer.append(d)
            if len(safe) >= 2 and len(closer) == 1:
                out.append(
                    {
                        "dirs": dict(sc.build_state(g)["directions"]),
                        "full": sc.build_state(g),
                        "criteria": sc.build_criteria(g),
                        "answer": closer[0],
                        "n_options": len(g.options()),
                        "n_safe": len(safe),
                    }
                )
                if len(out) >= n:
                    break
            g.step(rng.choice(safe))
            if not g.alive:
                break
    return out


# ---- 試す言い回し --------------------------------------------------------
# 迷路で効いたのは「正解の選択肢にだけ出る語を、指示にも書く」だった。
# Snakeでも同じ形をいくつか試す。

def words(good: str, other: str, blocked: str):
    def build(case):
        out = {}
        for d, v in case["dirs"].items():
            if v == "blocked":
                out[d] = blocked
            elif "toward" in v:
                out[d] = good
            else:
                out[d] = other
        return {"directions": out}
    return build


NEVER = "Never choose blocked. "

VARIANTS = {
    "A 共通語を持たせる（最初の版）": (
        words("open, closer to the apple", "open, farther from the apple", "blocked"),
        f"{sc.QUESTION} Read `directions`. Choose a direction that is open. "
        "Among the open directions, choose the one that is closer to the apple.",
    ),
    "B 正解だけに apple を出す": (
        words("toward the apple", "away", "blocked"),
        f"{sc.QUESTION} Read `directions`. Choose the direction that is toward the apple.",
    ),
    "C B＋死ぬ手を名指しで禁じる": (
        words("toward the apple", "away", "blocked"),
        f"{sc.QUESTION} Read `directions`. {NEVER}"
        "Choose the direction that is toward the apple.",
    ),
    "D 良し悪しを言い切る": (
        words("good", "bad", "deadly"),
        f"{sc.QUESTION} Read `directions`. Choose the direction that is good.",
    ),
    "E いまの本番設定": (
        None,
        f"{sc.QUESTION} {sc.FOCUS}",
    ),
}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=80)
    ap.add_argument("--jev", action="store_true")
    ap.add_argument("--checkpoint", default="multilingual")
    args = ap.parse_args()

    cases = collect(args.n)
    base = sum(1 / c["n_safe"] for c in cases) / len(cases) * 100
    print(f"局面 {len(cases)} 件（安全な手が2つ以上、近づく手はちょうど1つ）")
    print(f"当てずっぽうの期待値: {base:.1f}%\n")

    import laya

    agent = laya.load(
        "convaiinnovations/laya",
        subfolder=None if args.checkpoint == "english" else args.checkpoint,
    )
    print(f"=== Laya / {args.checkpoint} ===")
    for label, (build, instr) in VARIANTS.items():
        ok = 0
        lat = []
        for c in cases:
            payload = c["full"] if build is None else build(c)
            t = time.perf_counter()
            r = agent.predict(
                payload,
                {"direction": {"type": "choice", "instructions": instr, "criteria": c["criteria"]}},
            )
            lat.append((time.perf_counter() - t) * 1000)
            if r["answers"]["direction"]["choice"] == c["answer"]:
                ok += 1
        print(f"  {label:26} 正答 {ok:3}/{len(cases)} ({ok / len(cases) * 100:5.1f}%)  "
              f"{sum(lat) / len(lat):5.1f}ms")

    if args.jev:
        from typesafe_sdk import Choice, TypeSafeClient

        print("\n=== Jev（同じ局面・全部の欄） ===")
        with TypeSafeClient() as client:
            ok = 0
            for c in cases:
                r = client.system_one(
                    state=c["full"],
                    questions={
                        "direction": Choice(
                            instructions={
                                "question": sc.QUESTION,
                                "inspect": "`directions`, `apple`, `snake`",
                                "focus": sc.FOCUS,
                            },
                            criteria=c["criteria"],
                        )
                    },
                )
                if r.answers["direction"].choice == c["answer"]:
                    ok += 1
            print(f"  {'構造化した指示':26} 正答 {ok:3}/{len(cases)} ({ok / len(cases) * 100:5.1f}%)")


if __name__ == "__main__":
    main()
