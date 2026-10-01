"""迷路そのものと、Jevに渡す「状態」の組み立て。

CLI版（maze.py）とWeb版（server.py）で共有する。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

MOVES: dict[str, tuple[int, int]] = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}

DIRECTIONS = tuple(MOVES)

# 質問文。公式の書き方（question / inspect / focus）に合わせて構造化する。
#
# focus の中身は実測で決めた。
# 「ゴールに向かって進め」としか書かなかったときは、モデルは 12/12 で
# ゴールへの直線距離が縮む向きを選び、壁に阻まれて同じ場所を往復し続けた。
# 迷路で貪欲法が失敗するのは当たり前で、モデルの落ち度ではなく質問文の落ち度。
# 後戻りの扱いを明示したら 20/20 で解けるようになった。
INSTRUCTIONS = {
    "question": "Which direction should the explorer move next to get out of this maze?",
    "inspect": "`maze.grid`, `explorer`, `goal`, `already_visited`",
    "focus": (
        "Walls block the straight line to the goal, so the direction that looks "
        "closer is often a dead end you have already explored. Prefer a cell you "
        "have never visited. Only step onto a visited cell when every other option "
        "is also visited."
    ),
}

@dataclass
class Maze:
    rows: int = 11
    cols: int = 15
    seed: int | None = None
    grid: list[list[str]] = field(default_factory=list)
    pos: tuple[int, int] = (1, 1)
    start: tuple[int, int] = (1, 1)
    goal: tuple[int, int] = (1, 1)
    trail: list[tuple[int, int]] = field(default_factory=list)
    visits: dict[tuple[int, int], int] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.grid:
            self.generate()

    # ------------------------------------------------------------------ 生成

    def generate(self) -> None:
        """再帰的バックトラッカーで迷路を掘る。行・列は奇数にそろえる。"""
        rows = self.rows if self.rows % 2 else self.rows + 1
        cols = self.cols if self.cols % 2 else self.cols + 1
        self.rows, self.cols = rows, cols

        rng = random.Random(self.seed)
        grid = [["#"] * cols for _ in range(rows)]

        # 31x31 くらいになると再帰では Python のスタックが尽きる。明示スタックで掘る。
        stack = [(1, 1)]
        grid[1][1] = "."
        while stack:
            r, c = stack[-1]
            dirs = [(-2, 0), (2, 0), (0, -2), (0, 2)]
            rng.shuffle(dirs)
            for dr, dc in dirs:
                nr, nc = r + dr, c + dc
                if 0 < nr < rows - 1 and 0 < nc < cols - 1 and grid[nr][nc] == "#":
                    grid[r + dr // 2][c + dc // 2] = "."
                    grid[nr][nc] = "."
                    stack.append((nr, nc))
                    break
            else:
                stack.pop()

        self.grid = grid
        self.start = (1, 1)
        self.goal = (rows - 2, cols - 2)
        self.grid[self.goal[0]][self.goal[1]] = "."
        self.reset()

    def reset(self) -> None:
        self.pos = self.start
        self.trail = [self.start]
        self.visits = {self.start: 1}

    # -------------------------------------------------------------- 盤面の問い合わせ

    def is_wall(self, pos: tuple[int, int]) -> bool:
        r, c = pos
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return True
        return self.grid[r][c] == "#"

    def legal_moves(self) -> list[str]:
        r, c = self.pos
        return [
            name for name, (dr, dc) in MOVES.items() if not self.is_wall((r + dr, c + dc))
        ]

    def move(self, name: str) -> bool:
        """動けたらTrue、壁に突っ込んだらFalse。"""
        dr, dc = MOVES[name]
        nxt = (self.pos[0] + dr, self.pos[1] + dc)
        if self.is_wall(nxt):
            return False
        self.pos = nxt
        self.trail.append(nxt)
        self.visits[nxt] = self.visits.get(nxt, 0) + 1
        return True

    def at_goal(self) -> bool:
        return self.pos == self.goal

    def shortest_path(self) -> list[tuple[int, int]]:
        """最短経路。Jevには渡さない。オフラインモードと答え合わせにだけ使う。"""
        from collections import deque

        prev: dict[tuple[int, int], tuple[int, int] | None] = {self.pos: None}
        queue = deque([self.pos])
        while queue:
            cur = queue.popleft()
            if cur == self.goal:
                break
            for dr, dc in MOVES.values():
                nxt = (cur[0] + dr, cur[1] + dc)
                if nxt not in prev and not self.is_wall(nxt):
                    prev[nxt] = cur
                    queue.append(nxt)
        if self.goal not in prev:
            return []
        path, node = [], self.goal
        while node is not None:
            path.append(node)
            node = prev[node]
        return list(reversed(path))

    # ------------------------------------------------------------------ 描画

    def render(self) -> str:
        out = []
        for r, row in enumerate(self.grid):
            line = []
            for c, cell in enumerate(row):
                if (r, c) == self.pos:
                    line.append("@")
                elif (r, c) == self.goal:
                    line.append("G")
                else:
                    line.append(cell)
            out.append("".join(line))
        return "\n".join(out)

    def as_dict(self) -> dict:
        return {
            "rows": self.rows,
            "cols": self.cols,
            "grid": ["".join(row) for row in self.grid],
            "pos": list(self.pos),
            "start": list(self.start),
            "goal": list(self.goal),
            "trail": [list(p) for p in self.trail],
            "legalMoves": self.legal_moves(),
            "atGoal": self.at_goal(),
            "maxRevisits": max(self.visits.values()) if self.visits else 0,
        }


def forward_moves(maze: Maze) -> list[str]:
    """来た道を除いて、進める方向。

    迷路の大半はただの通路なので、ここが1つに定まるマスが9割を超える。
    そこでモデルに聞いても「そのまま進め」しか返ってこない。
    """
    prev = maze.trail[-2] if len(maze.trail) >= 2 else None
    out = []
    for name in maze.legal_moves():
        dr, dc = MOVES[name]
        if prev == (maze.pos[0] + dr, maze.pos[1] + dc):
            continue
        out.append(name)
    # 行き止まりで戻るしかないときは、戻る手を潰さない
    return out or maze.legal_moves()


def _neighbour(maze: Maze, name: str) -> tuple[int, int]:
    dr, dc = MOVES[name]
    return (maze.pos[0] + dr, maze.pos[1] + dc)


def build_criteria(maze: Maze, legal_hint: bool = True) -> dict[str, str]:
    """Choice の選択肢。

    壁の方向まで選択肢に入れると、取れない手に確率が配られる。
    confidence は分布の尖り具合から計算されるので、
    取れない手が混じるだけで「自信がない」と誤って読めてしまう。
    なので既定では実際に取れる手だけを並べる。

    legal_hint=False のときだけ4方向すべてを出す。
    こちらは「壁をモデルに推測させられるか」を試すための、意図的な逸脱。
    """
    names = maze.legal_moves() if legal_hint else list(DIRECTIONS)
    out = {}
    for name in names:
        r, c = _neighbour(maze, name)
        seen = maze.visits.get((r, c), 0)
        been = (
            "never been there"
            if seen == 0
            else f"already been there {seen} time{'s' if seen > 1 else ''}"
        )
        out[name] = f"Step to row {r}, column {c}; you have {been}"
    return out


def build_state(maze: Maze, legal_hint: bool = True, trail_length: int = 8) -> dict:
    """Jevに渡す状態。

    公式ドキュメントは「各部分に名前が付くので、ほとんどの場合はオブジェクトを使う」
    としている。文字列1本に固めない。
    """
    state: dict = {
        "legend": {
            "#": "wall",
            ".": "open corridor",
            "@": "the explorer, which is you",
            "G": "the goal",
        },
        "maze": {
            "rows": maze.rows,
            "cols": maze.cols,
            "grid": maze.render().split("\n"),
        },
        "explorer": {"row": maze.pos[0], "col": maze.pos[1]},
        "goal": {"row": maze.goal[0], "col": maze.goal[1]},
    }
    if legal_hint:
        state["open_directions"] = maze.legal_moves()
    recent = maze.trail[-trail_length:]
    if len(recent) > 1:
        state["just_came_from"] = [{"row": r, "col": c} for r, c in recent[:-1]]
    # 訪問済みの全マス。これが無いと、長い迂回のあとに戻ってきた分岐で
    # 「その枝はもう見た」とモデルが知る手段が無く、判断のしようがない。
    if maze.visits:
        state["already_visited"] = [
            {"row": r, "col": c, "times": n}
            for (r, c), n in sorted(maze.visits.items())
        ]
    return state
