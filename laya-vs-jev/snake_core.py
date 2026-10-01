"""Snakeの盤面と、モデルに渡す状態・質問。

迷路で踏んだ穴をここでは最初から避けている。

1. **判断に要る事実は state に置く。** 選択肢の説明文にだけ書くと、Layaは読まない
   （盤面と照合して選ぶ仕組みなので、文にしかない事実は効かない）。実測で確認した。
2. **指示と状態で同じ語を重ねない。** "unvisited" と "visited 3 times" のように
   片方がもう片方を含むと、Layaは逆を選ぶ（60問中0問正解になった）。
3. **選択肢は取れる手だけ。** 壁や自分の体に突っ込む手を混ぜると、取れない手に
   確率が配られて confidence が不当に下がる。
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
OPPOSITE = {"up": "down", "down": "up", "left": "right", "right": "left"}

QUESTION = "Which direction should the snake move next?"
# 文面は実測で決めた。最初はこう書いていた:
#   "Moving onto a wall or onto the snake's own body ends the game at once.
#    ... never pick one that ends the game. ... brings the head closer to the apple"
# これだと、死ぬ手の説明（"the game ends"）が指示の語（"ends the game"）と重なり、
# Layaは死ぬ手を選びやすかった（安全補正3.2%）。directions の書き方も同時に変えたので、
# 語の重なりだけが原因とは言い切れない。
# 指示に出す語を、正解の選択肢にだけ出るようにしたら 2/2（0.85）になった。
# 文面と state の語は実測で決めた。80局面で測った正答率:
#   "open, closer to the apple" / "open, farther from the apple" / "blocked"  → 12.5%
#   "toward the apple"          / "away"                         / "blocked"  → 100%
# 違いは、見分ける語（apple）が正解の選択肢にだけ出るかどうか。
# さらに、死ぬ手を名指しで禁じる一文（Never choose blocked）を足すと、
# 120局面で自殺手0%・りんご方向100%になった。足さないと5.0%/88.5%。
# 共通の語を持たせると、そちらに引っ張られて当てずっぽう（34.4%）より下になる。
FOCUS = (
    "Read `directions`. Never choose blocked. "
    "Choose the direction that is toward the apple."
)

# 袋小路（打ったあとに蛇が入りきらない空間しか残らない手）をどう伝えるか。
# 既定は伝えない。実測の結果:
#
#   1000判断あたり          Jev 食 / 詰み / 安全補正     Laya 食 / 詰み / 安全補正
#   none（伝えない）        64.1 / 2.0 / 0.0%            39.5 / 1.0 / 0.4%
#   trap_word（trap を追加）49.0 / 0.0 / 2.3%            33.0 / 0.5 / 2.2%
#   as_blocked（blockedと呼ぶ）51.0 / 0.0 / 0.3%          38.0 / 1.0 / 1.4%
#
# 詰みは1000判断に1〜2回しか起きないので「2回が0回」は効いたと言い切れない。
# 一方で食べる数は2割落ち、trap という語を指示に足すと**両モデルとも**
# 即死手を選ぶ割合が2%台に跳ね上がる（Jevは0.0%から）。
# trap の方向は即死しないので、増えたのは blocked を選んだ割合。禁止をもう1つ足したら、
# もとの禁止（Never choose blocked）が守られなくなった。Laya固有ではない。
TRAP_MODES = ("none", "as_blocked", "trap_word")

FOCUS_TRAP_WORD = (
    "Read `directions`. Never choose blocked. Never choose trap. "
    "Choose the direction that is toward the apple."
)


def focus_for(trap_mode: str = "none") -> str:
    return FOCUS_TRAP_WORD if trap_mode == "trap_word" else FOCUS


@dataclass
class Snake:
    rows: int = 18
    cols: int = 24
    seed: int | None = None
    body: list[tuple[int, int]] = field(default_factory=list)   # 先頭が頭
    heading: str = "right"
    apple: tuple[int, int] = (0, 0)
    score: int = 0
    alive: bool = True
    cause: str = ""

    def __post_init__(self) -> None:
        self.rng = random.Random(self.seed)
        r, c = self.rows // 2, self.cols // 4
        self.body = [(r, c), (r, c - 1), (r, c - 2)]
        self.heading = "right"
        self.place_apple()

    # ------------------------------------------------------------ 盤面

    def place_apple(self) -> None:
        free = [
            (r, c)
            for r in range(self.rows)
            for c in range(self.cols)
            if (r, c) not in self.body
        ]
        self.apple = self.rng.choice(free) if free else self.body[0]

    def head(self) -> tuple[int, int]:
        return self.body[0]

    def cell_after(self, name: str) -> tuple[int, int]:
        dr, dc = MOVES[name]
        r, c = self.body[0]
        return (r + dr, c + dc)

    def fatal(self, name: str) -> str | None:
        """その手で死ぬなら理由を返す。死なないなら None。"""
        r, c = self.cell_after(name)
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return "wall"
        # しっぽは同時に動くので、りんごを食べない限り空く
        tail = self.body[-1]
        body = set(self.body[:-1]) if (r, c) != self.apple else set(self.body)
        if (r, c) in body and (r, c) != tail:
            return "body"
        return None

    def options(self) -> list[str]:
        """来た方向の逆は選べない（Snakeの決まり）。"""
        return [n for n in MOVES if n != OPPOSITE[self.heading]]

    def safe_options(self) -> list[str]:
        return [n for n in self.options() if self.fatal(n) is None]

    def open_space(self, name: str) -> int:
        """その手を打ったあと、頭から届く空きマスの数。袋小路の検出に使う。"""
        start = self.cell_after(name)
        if self.fatal(name):
            return 0
        blocked = set(self.body[:-1])
        seen = {start}
        stack = [start]
        while stack:
            r, c = stack.pop()
            for dr, dc in MOVES.values():
                n = (r + dr, c + dc)
                if (
                    0 <= n[0] < self.rows
                    and 0 <= n[1] < self.cols
                    and n not in seen
                    and n not in blocked
                ):
                    seen.add(n)
                    stack.append(n)
        return len(seen)

    def step(self, name: str) -> bool:
        """進める。死んだら False。"""
        why = self.fatal(name)
        if why:
            self.alive = False
            self.cause = why
            return False
        self.heading = name
        nxt = self.cell_after(name)
        self.body.insert(0, nxt)
        if nxt == self.apple:
            self.score += 1
            self.place_apple()
        else:
            self.body.pop()
        return True


# ---------------------------------------------------------------- 質問


def is_trap(s: "Snake", name: str) -> bool:
    """その手のあと、蛇が入りきらない空間しか残らないか。入ったらいつか必ず詰む。"""
    return s.open_space(name) <= len(s.body)


def build_state(s: Snake, trap_mode: str = "none") -> dict:
    """モデルに渡す状態。

    判断に要るのは「その方向に何があるか」と「りんごがどちらか」。
    盤面のASCIIも入れるが、方向ごとの事実は `directions` に明示する。
    """
    hr, hc = s.head()
    ar, ac = s.apple

    # 方向ごとの事実は、必ずこの1つの欄にまとめる。
    # 欄を分けると（安全の欄とりんごの欄）、Layaは片方しか読まなかった（入れ替えテスト 1/2）。
    # 距離を数字で渡すのも効かない（0/2）。言葉で書く。
    directions = {}
    for name in s.options():
        if s.fatal(name):
            # 指示文と語を共有させない。"crashes ... the game ends" と書いていたときは即死手が3.2%だった。
            directions[name] = "blocked"
            continue
        if trap_mode != "none" and is_trap(s, name):
            directions[name] = "blocked" if trap_mode == "as_blocked" else "trap"
            continue
        r, c = s.cell_after(name)
        closer = abs(r - ar) + abs(c - ac) < abs(hr - ar) + abs(hc - ac)
        directions[name] = "toward the apple" if closer else "away"

    # 欄はこれだけ。盤面の大きさ・頭の座標・りんごの座標も足していたが、
    # 足すと Laya の正答率が 100% → 6.2% まで落ちた（diagnose_snake.py の条件E）。
    # この問いに要るのは方向ごとの事実だけなので、公式の指針どおり先に絞って送る。
    # Jev にも同じものを渡す（土俵を揃えるため）。
    return {"directions": directions}


def build_criteria(s: Snake) -> dict[str, str]:
    return {name: f"move {name}" for name in s.options()}
