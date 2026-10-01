#!/usr/bin/env python3
"""迷路でLayaが出口にたどり着けないのは、設定のせいか、判断そのものか。

迷路の結果（ゴールしたか）だけ見ても切り分けられない。1手でも間違えば
遠回りになるし、たまたま当たることもある。

そこで、**答えが決まっている分岐だけ**を集めて正答率を見る。

  「未訪問の枝が1つだけあり、ほかは全部訪問済み」

この形なら、未訪問を選ぶのが正解。質問文にも「未訪問を優先しろ」と明示してある。
ここを外すなら、迷路の難しさではなく判断の問題。1本目でJevに使った指標と同じ
（Jevは 46/46 = 100%）。

使い方:
    python diagnose.py --n 60
    python diagnose.py --n 60 --jev     # Jevも同じ問題で測る（APIを使う）
"""

from __future__ import annotations

import argparse
import time

from maze_core import Maze, forward_moves
import players


def collect(n: int, size: int = 21) -> list[dict]:
    """「未訪問が1つだけ」の分岐を集める。"""
    out: list[dict] = []
    seed = 0
    while len(out) < n and seed < 400:
        maze = Maze(rows=size, cols=size, seed=seed)
        seed += 1
        for _ in range(size * size * 2):
            if maze.at_goal():
                break
            options = forward_moves(maze)
            if len(options) > 1:
                unseen = [d for d in options if not maze.visits.get(players._cell(maze, d))]
                if len(unseen) == 1 and len(options) >= 2:
                    out.append(
                        {
                            "state": players.build_state(maze),
                            "criteria": {k: f"move {k}" for k in options},
                            "answer": unseen[0],
                            "options": list(options),
                        }
                    )
                    if len(out) >= n:
                        break
                maze.move((unseen or options)[0])
            else:
                maze.move(options[0])
    return out


# ---- 試す設定 -------------------------------------------------------------

SHORT = "Which direction should the explorer move next?"
FOCUS = players.FOCUS


# 直す前の書き方。"unvisited" と "visited" が語として重なり、Layaは逆を選んだ。
OLD_FOCUS = (
    "Walls block the straight line to the goal, so the direction that looks closer "
    "is often a dead end you have already explored. Prefer a cell you have never "
    "visited. Only step onto a visited cell when every other option is also visited."
)

def strip_view(state: dict) -> dict:
    """判断に要らないものを落とす。この問いに必要なのは `directions` だけ。"""
    return {"directions": state["directions"]}


CONFIGS = {
    "A 直したあと": lambda c: (f"{players.QUESTION} {FOCUS}", c, {}),
    "B 指示を短く（focusなし）": lambda c: (SHORT, c, {}),
    "C 直す前の言い回し": lambda c: (f"{players.QUESTION} {OLD_FOCUS}", c, {}),
    "D lang=en を明示": lambda c: (f"{players.QUESTION} {FOCUS}", c, {"lang": "en"}),
    "E 窓を外す（directionsだけ）": lambda c: (f"{players.QUESTION} {FOCUS}", c, {}),
}


def run_laya(cases: list[dict], checkpoint: str) -> None:
    import laya

    agent = laya.load(
        "convaiinnovations/laya", subfolder=None if checkpoint == "english" else checkpoint
    )
    print(f"\n=== Laya / {checkpoint} ===")
    for label, make in CONFIGS.items():
        ok = 0
        lat = []
        margins = []
        for case in cases:
            instr, crit, extra = make(case["criteria"])
            st = strip_view(case["state"]) if label.startswith("E ") else case["state"]
            t = time.perf_counter()
            r = agent.predict(
                st,
                {"direction": {"type": "choice", "instructions": instr, "criteria": crit}},
                **extra,
            )
            lat.append((time.perf_counter() - t) * 1000)
            a = r["answers"]["direction"]
            if a["choice"] == case["answer"]:
                ok += 1
            p = a.get("probabilities", {})
            if p:
                s = sorted(p.values(), reverse=True)
                margins.append(s[0] - (s[1] if len(s) > 1 else 0))
        avg_margin = sum(margins) / len(margins) if margins else 0
        print(
            f"  {label:26} 正答 {ok:3}/{len(cases)} ({ok / len(cases) * 100:5.1f}%)  "
            f"1位と2位の差 {avg_margin:.3f}  {sum(lat) / len(lat):5.1f}ms"
        )


def run_jev(cases: list[dict]) -> None:
    from typesafe_sdk import Choice, TypeSafeClient

    print("\n=== Jev（同じ問題） ===")
    with TypeSafeClient() as client:
        ok = 0
        margins = []
        for case in cases:
            r = client.system_one(
                state=case["state"],
                questions={
                    "direction": Choice(
                        instructions={
                            "question": players.QUESTION,
                            "inspect": "`view`",
                            "focus": FOCUS,
                        },
                        criteria=case["criteria"],
                    )
                },
            )
            a = r.answers["direction"]
            if a.choice == case["answer"]:
                ok += 1
            s = sorted(a.probabilities.values(), reverse=True)
            margins.append(s[0] - (s[1] if len(s) > 1 else 0))
        print(
            f"  {'構造化した指示':26} 正答 {ok:3}/{len(cases)} ({ok / len(cases) * 100:5.1f}%)  "
            f"1位と2位の差 {sum(margins) / len(margins):.3f}"
        )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=60)
    ap.add_argument("--jev", action="store_true")
    ap.add_argument("--checkpoints", default="typed-decisions,multilingual,english")
    args = ap.parse_args()

    cases = collect(args.n)
    print(f"「未訪問が1つだけ」の分岐を {len(cases)} 件 集めた（正解は常に未訪問の枝）")
    print(f"当てずっぽうの期待値: {sum(1 / len(c['options']) for c in cases) / len(cases) * 100:.1f}%")

    for ck in args.checkpoints.split(","):
        run_laya(cases, ck.strip())
    if args.jev:
        run_jev(cases)


if __name__ == "__main__":
    main()
