"""JevとLayaに、まったく同じ迷路・まったく同じ質問を投げるための層。

比較の公平さのために決めたこと:

1. **状態は両者で同じものを使う。**
   Jevは1リクエスト64kトークン入るが、Layaのチェックポイントは1024（multilingualは
   8192まで拡張可）。盤面のASCIIを丸ごと渡すとLayaだけが溢れる。
   どちらにも入る大きさに切りそろえた「探索者の周囲だけを見せる窓」を使う。
   Jevに有利な条件で測って「Layaが負けた」と書かないため。

2. **モデルに聞くのは本当の分岐だけ。** 一本道はコードで進む。
   1本目の計測で、毎手聞かせると遅く高くなるうえ解けなくなることが分かっている。
   この規則は両者に同じく適用する。

3. **選択肢は実際に取れる手だけ。** 壁の方向を混ぜると、取れない手に確率が
   配られて confidence が不当に下がる。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from maze_core import MOVES, Maze, forward_moves

# 質問文。1本目の実験で決めた文面をそのまま使う（焦点を書かないと貪欲法で往復する）。
QUESTION = "Which direction should the explorer move next to get out of this maze?"
FOCUS = (
    "Walls block the straight line to the goal, so the direction that looks closer "
    "is often a dead end you already explored. Read `directions`: choose a direction "
    "where you have never been. Only go back somewhere you have been before when "
    "every direction is somewhere you have been before."
)

VIEW = 11  # 探索者を中心に見せる窓の一辺（奇数）


@dataclass
class Decision:
    direction: str
    probabilities: dict[str, float]
    confidence: float | None
    latency_ms: float
    asked: bool  # モデルに聞いたか、コードで決めたか
    reason: str = ""
    tokens_in: int = 0


@dataclass
class Stats:
    moves: int = 0
    calls: int = 0
    infer_ms: float = 0.0
    wall_ms: float = 0.0
    finished: bool = False
    history: list[Decision] = field(default_factory=list)


def build_state(maze: Maze) -> dict:
    """探索者の周囲 VIEW×VIEW だけを渡す。両モデルに同じものを渡す。

    盤面全体を渡さないので「地図を読んで最短を引く」ことはできない。
    どちらのモデルも同じ条件で、手元の分岐を判断する。
    """
    half = VIEW // 2
    r0, c0 = maze.pos[0] - half, maze.pos[1] - half
    view = []
    for r in range(r0, r0 + VIEW):
        row = []
        for c in range(c0, c0 + VIEW):
            if not (0 <= r < maze.rows and 0 <= c < maze.cols):
                row.append("#")
            elif (r, c) == maze.pos:
                row.append("@")
            elif (r, c) == maze.goal:
                row.append("G")
            elif maze.visits.get((r, c)):
                row.append("o")  # 歩いたことのあるマス
            else:
                row.append(maze.grid[r][c])
        view.append("".join(row))

    dr = maze.goal[0] - maze.pos[0]
    dc = maze.goal[1] - maze.pos[1]

    # 各方向の「行ったことがあるか」は state に置く。
    # 選択肢の説明文にだけ書いて、窓の中の記号と突き合わせさせるのは間接参照になる。
    # Jevはそれでも解けたが、Layaは選択肢の文を state と照合して選ぶので、
    # 文にしか書いていない事実は判断に効かない（実測で確認した）。
    #
    # 言い回しも実測で決めた。"unvisited" / "visited 3 times" と書くと、
    # 両方に visited が入っているせいで Laya は逆を選ぶ（60問中0問正解）。
    # 語を重ねない書き方にする。
    history = {}
    for name in forward_moves(maze):
        seen = maze.visits.get(_cell(maze, name), 0)
        history[name] = (
            "never been there"
            if seen == 0
            else f"been there {seen} time{'s' if seen > 1 else ''}"
        )

    return {
        "legend": {
            "#": "wall",
            ".": "open corridor you have never walked",
            "o": "open corridor you have already walked",
            "@": "the explorer, which is you",
            "G": "the goal",
        },
        "view": {
            "note": f"a {VIEW} by {VIEW} window centred on the explorer",
            "rows": view,
        },
        "goal_offset": {"rows_down": dr, "cols_right": dc},
        "open_directions": maze.legal_moves(),
        "directions": history,
    }


class CodePlayer:
    """モデルを使わない基準線。来た道以外が1つならそれ、分岐では未訪問を優先。"""

    name = "コード（基準線）"
    badge = "no model"

    def decide(self, maze: Maze) -> Decision:
        options = forward_moves(maze)
        unseen = [d for d in options if not maze.visits.get(_cell(maze, d))]
        pick = (unseen or options)[0]
        return Decision(pick, {}, None, 0.0, asked=False, reason="code")


def _cell(maze: Maze, name: str) -> tuple[int, int]:
    dr, dc = MOVES[name]
    return (maze.pos[0] + dr, maze.pos[1] + dc)


class JevPlayer:
    name = "Jev"
    badge = "API / 大阪から"

    def __init__(self) -> None:
        from typesafe_sdk import TypeSafeClient

        self.client = TypeSafeClient()
        self.model = "jev"

    def close(self) -> None:
        self.client.close()

    def decide(self, maze: Maze) -> Decision:
        from typesafe_sdk import Choice

        criteria = {k: f"move {k}" for k in forward_moves(maze)}
        started = time.perf_counter()
        res = self.client.system_one(
            state=build_state(maze),
            questions={
                "direction": Choice(
                    instructions={"question": QUESTION, "inspect": "`view`, `directions`", "focus": FOCUS},
                    criteria=criteria,
                )
            },
        )
        ms = (time.perf_counter() - started) * 1000
        a = res.answers["direction"]
        return Decision(
            a.choice,
            dict(a.probabilities),
            a.confidence,
            ms,
            asked=True,
            tokens_in=res.usage.input_tokens,
        )


class LayaPlayer:
    badge = "ローカル / M1 Ultra"

    def __init__(self, checkpoint: str | None = "multilingual", backend: str = "mlx") -> None:
        # backend="mlx" は非公式の移植版。本家と答えが 200/200 一致、p50 は 2.1倍速い。
        if backend == "mlx":
            import laya_mlx as backend_mod
        else:
            import laya as backend_mod

        self.checkpoint = checkpoint or "english"
        self.backend = backend
        self.name = f"Laya ({self.checkpoint})"
        self.badge = f"ローカル / M1 Ultra · {'MLX' if backend == 'mlx' else 'PyTorch'}"
        self.agent = backend_mod.load(
            "convaiinnovations/laya", subfolder=checkpoint if checkpoint != "english" else None
        )

    def close(self) -> None:
        pass

    def decide(self, maze: Maze) -> Decision:
        criteria = {k: f"move {k}" for k in forward_moves(maze)}
        started = time.perf_counter()
        res = self.agent.predict(
            build_state(maze),
            {
                "direction": {
                    "type": "choice",
                    "instructions": f"{QUESTION} {FOCUS}",
                    "criteria": criteria,
                }
            },
        )
        ms = (time.perf_counter() - started) * 1000
        a = res["answers"]["direction"]
        return Decision(
            a["choice"],
            dict(a.get("probabilities", {})),
            a.get("confidence"),
            ms,
            asked=True,
            tokens_in=res.get("usage", {}).get("input_tokens", 0),
        )


def step(player, maze: Maze) -> Decision:
    """1手進める。分岐でないマスはモデルに聞かない。"""
    options = forward_moves(maze)
    if len(options) == 1:
        maze.move(options[0])
        return Decision(options[0], {}, None, 0.0, asked=False, reason="一本道（分岐ではない）")
    d = player.decide(maze)
    if d.direction not in options:
        # 取れない手が返ったときは、質問に無い手なので弾く
        d.reason = f"選択肢にない手 {d.direction} が返ったので棄却"
        d.direction = options[0]
    maze.move(d.direction)
    return d
