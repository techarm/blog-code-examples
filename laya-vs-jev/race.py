#!/usr/bin/env python3
"""JevとLayaに同じ迷路を同時に解かせる。

    python race.py                      # Jev vs Laya（typed-decisions）
    python race.py --size 25 --seed 3
    python race.py --laya multilingual
    python race.py --mock               # APIもモデルも使わず見た目だけ確認する
    python race.py --record frames      # 画面を出さずに、実時間のまま1コマずつPNGで書き出す
    python race.py --replay frames      # 走り終わってから、手数をそろえて描き直す（frames_to_webp.py で動画にする）

見るべきは実時間ではなく**手数**。Jevは太平洋を往復し、Layaは手元で動くので、
実時間はネットワークの差をそのまま映す。判断の質が出るのは手数とモデル呼び出し回数。
"""

from __future__ import annotations

import argparse
import os
import random
import threading
import time

import pygame

from maze_core import Maze, forward_moves
import players

# ---------------------------------------------------------------- 配色

BG = (13, 17, 23)
PANEL = (22, 27, 34)
PANEL_EDGE = (48, 54, 61)
WALL = (38, 45, 56)
FLOOR = (16, 21, 28)
TEXT = (230, 237, 243)
MUTED = (125, 138, 153)
DIM = (72, 82, 95)

JEV = (88, 166, 255)
JEV_SOFT = (33, 61, 97)
LAYA = (255, 166, 87)
LAYA_SOFT = (92, 60, 26)
GOAL = (87, 217, 142)
WIN = (255, 214, 102)
DETOUR = (240, 96, 96)


# 画面の文言は日本語なので、日本語を持っているフォントを明示的に探す。
# pygame の既定フォントには日本語が入っておらず、全部豆腐になる。
_FONT_CANDIDATES = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)
_FONT_PATH: str | None = None
_FONT_CACHE: dict[tuple[int, bool], pygame.font.Font] = {}


def _font_path() -> str | None:
    global _FONT_PATH
    if _FONT_PATH is None:
        for cand in _FONT_CANDIDATES:
            if os.path.exists(cand):
                _FONT_PATH = cand
                break
        else:
            _FONT_PATH = ""
    return _FONT_PATH or None


def font(size: int, bold: bool = False) -> pygame.font.Font:
    key = (size, bold)
    if key not in _FONT_CACHE:
        path = _font_path()
        f = pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
        f.set_bold(bold and path is not None)
        _FONT_CACHE[key] = f
    return _FONT_CACHE[key]


# ---------------------------------------------------------------- 走者


class Runner:
    """1人ぶんの走行。別スレッドで回し、描画スレッドは結果だけ読む。"""

    def __init__(self, player, maze: Maze, limit: int) -> None:
        self.player = player
        self.maze = maze
        self.limit = limit
        self.stats = players.Stats()
        self.last: players.Decision | None = None
        self.error: str | None = None
        self.lock = threading.Lock()
        self.started_at = 0.0
        # 未踏の道があるのに、通ったことのある道を選んだ分かれ道。
        # 指示では「行ったことがない方を選べ」と言っているので、これは規則に反した選択。
        # 画面ではここを赤く囲み、同じ分かれ道に戻ってくるまでの遠回りを赤で描く。
        self.detours: list[dict] = []
        # 1手ごとの数字。--replay で、手数をそろえて描き直すときに使う
        self.snapshots: list[dict] = []
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.started_at = time.perf_counter()
        self.thread.start()

    def _run(self) -> None:
        try:
            while not self.maze.at_goal() and self.stats.moves < self.limit:
                m = self.maze
                at, start = m.pos, len(m.trail) - 1
                unseen = [o for o in forward_moves(m) if not m.visits.get(players._cell(m, o))]
                d = players.step(self.player, m)
                with self.lock:
                    if d.asked and unseen and d.direction not in unseen:
                        self.detours.append({"at": at, "start": start})
                    self.stats.moves += 1
                    if d.asked:
                        self.stats.calls += 1
                        self.stats.infer_ms += d.latency_ms
                        self.stats.history.append(d)
                    self.last = d
                    self.stats.wall_ms = (time.perf_counter() - self.started_at) * 1000
                    self.snapshots.append({"calls": self.stats.calls, "infer_ms": self.stats.infer_ms,
                                           "wall_ms": self.stats.wall_ms, "last": d})
            with self.lock:
                self.stats.finished = self.maze.at_goal()
                self.stats.wall_ms = (time.perf_counter() - self.started_at) * 1000
        except Exception as exc:  # 片方が落ちても相手の走行は続ける
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"


class MockPlayer:
    """APIもモデルも使わない見た目確認用。"""

    badge = "mock"

    def __init__(self, name: str, ms: float, wrong: float) -> None:
        self.name = name
        self.ms = ms
        self.wrong = wrong
        self.rng = random.Random(0)

    def close(self) -> None:
        pass

    def decide(self, maze: Maze) -> players.Decision:
        time.sleep(self.ms / 1000)
        options = forward_moves(maze)
        unseen = [d for d in options if not maze.visits.get(players._cell(maze, d))]
        best = (unseen or options)[0]
        pick = self.rng.choice(options) if self.rng.random() < self.wrong else best
        p = {d: round(self.rng.uniform(0.1, 0.9), 3) for d in options}
        total = sum(p.values())
        p = {k: v / total for k, v in p.items()}
        return players.Decision(pick, p, max(p.values()), self.ms, asked=True)


class _MazeAt:
    """k手目の時点の迷路。歩いた跡を k手目で切るだけで、盤面は元の迷路のもの。"""

    def __init__(self, maze: Maze, k: int) -> None:
        self.rows, self.cols, self.grid = maze.rows, maze.cols, maze.grid
        self.start, self.goal = maze.start, maze.goal
        self.trail = maze.trail[: k + 1]
        self.pos = self.trail[-1]


class _RunnerAt:
    """k手目の時点の走者。draw_panel が読む属性だけを持つ。"""

    def __init__(self, runner: Runner, k: int) -> None:
        k = min(k, runner.stats.moves)
        self.player, self.limit, self.error = runner.player, runner.limit, None
        self.lock = threading.Lock()
        self.maze = _MazeAt(runner.maze, k)
        self.detours = [d for d in runner.detours if d["start"] < k]
        self.stats = players.Stats()
        self.stats.moves = k
        self.last = None
        if k:
            snap = runner.snapshots[k - 1]
            self.stats.calls, self.stats.infer_ms = snap["calls"], snap["infer_ms"]
            self.stats.wall_ms, self.last = snap["wall_ms"], snap["last"]
        self.stats.finished = runner.stats.finished and k == runner.stats.moves


# ---------------------------------------------------------------- 描画


def detour_span(maze: Maze, det: dict) -> list[tuple[int, int]]:
    """その分かれ道を出てから、同じ分かれ道に戻ってくるまでに歩いたマス。

    戻ってこなかった場合は空。通った道を選んでも、それがゴールへ向かう道なら
    遠回りではないので、線は引かない（丸だけ付ける）。
    """
    trail = maze.trail
    for i in range(det["start"] + 1, len(trail)):
        if trail[i] == det["at"]:
            return trail[det["start"]: i + 1]
    return []


def draw_maze(surf, rect, maze: Maze, colour, soft, detours=()) -> None:
    cell = min(rect.width // maze.cols, rect.height // maze.rows)
    ox = rect.x + (rect.width - cell * maze.cols) // 2
    oy = rect.y + (rect.height - cell * maze.rows) // 2

    pygame.draw.rect(surf, FLOOR, (ox, oy, cell * maze.cols, cell * maze.rows), border_radius=6)
    for r in range(maze.rows):
        for c in range(maze.cols):
            if maze.grid[r][c] == "#":
                pygame.draw.rect(surf, WALL, (ox + c * cell, oy + r * cell, cell, cell))

    # 歩いた跡。新しいほど濃い
    trail = maze.trail
    inset = max(cell // 4, 2)          # 細くして、下の通路の形が見えるようにする
    size = max(cell - inset * 2, 2)
    for i, (r, c) in enumerate(trail):
        t = i / max(len(trail) - 1, 1)
        col = tuple(int(soft[k] + (colour[k] - soft[k]) * (0.25 + 0.75 * t)) for k in range(3))
        pygame.draw.rect(surf, col, (ox + c * cell + inset, oy + r * cell + inset, size, size),
                         border_radius=2)

    # 規則に反した分かれ道と、そこからの遠回り
    for det in detours:
        for (r, c) in detour_span(maze, det):
            pygame.draw.rect(surf, DETOUR, (ox + c * cell + inset - 1, oy + r * cell + inset - 1,
                                            size + 2, size + 2), border_radius=2)
    for det in detours:
        r, c = det["at"]
        cx, cy = ox + c * cell + cell // 2, oy + r * cell + cell // 2
        pygame.draw.circle(surf, DETOUR, (cx, cy), cell, width=3)

    # スタートとゴールは、歩いた跡の上から印を描く。
    # 跡で埋まると、どこから出発したのか画面から分からなくなるため。
    def badge(pos, letter, fill, ring=None):
        r, c = pos
        cx, cy = ox + c * cell + cell // 2, oy + r * cell + cell // 2
        half = cell // 2 + 4
        box = pygame.Rect(cx - half, cy - half, half * 2, half * 2)
        if ring:
            pygame.draw.rect(surf, ring, box.inflate(6, 6), border_radius=7)
        pygame.draw.rect(surf, fill, box, border_radius=5)
        img = font(max(cell - 3, 11), True).render(letter, True, BG)
        surf.blit(img, img.get_rect(center=(cx, cy + 1)))

    badge(maze.start, "S", TEXT)

    r, c = maze.pos
    cx, cy = ox + c * cell + cell // 2, oy + r * cell + cell // 2
    if maze.pos != maze.goal:
        pygame.draw.circle(surf, colour, (cx, cy), max(cell // 2 + 2, 4))
        pygame.draw.circle(surf, (255, 255, 255), (cx, cy), max(cell // 4, 2))
        badge(maze.goal, "G", GOAL)
    else:
        # 着いたら、ゴールの印を自分の色で囲む
        badge(maze.goal, "G", GOAL, ring=colour)


def draw_metric(surf, x, y, label, value, colour=TEXT, w=120):
    surf.blit(font(13).render(label, True, MUTED), (x, y))
    surf.blit(font(26, True).render(value, True, colour), (x, y + 17))
    return x + w


def draw_panel(surf, rect, runner: Runner, colour, soft, shortest: int) -> None:
    pygame.draw.rect(surf, PANEL, rect, border_radius=14)
    pygame.draw.rect(surf, PANEL_EDGE, rect, width=1, border_radius=14)

    pad = 22
    x, y = rect.x + pad, rect.y + pad
    surf.blit(font(27, True).render(runner.player.name, True, colour), (x, y))
    badge = font(13).render(runner.player.badge, True, MUTED)
    bw = badge.get_width() + 16
    pygame.draw.rect(surf, soft, (rect.right - pad - bw, y + 4, bw, 24), border_radius=12)
    surf.blit(badge, (rect.right - pad - bw + 8, y + 9))

    with runner.lock:
        st = runner.stats
        moves, calls, infer, wall = st.moves, st.calls, st.infer_ms, st.wall_ms
        last, err, done = runner.last, runner.error, st.finished
        detours = list(runner.detours)

    maze_rect = pygame.Rect(x, y + 46, rect.width - pad * 2, rect.height - 232)
    draw_maze(surf, maze_rect, runner.maze, colour, soft, detours)

    my = maze_rect.bottom + 18
    ratio = f"{moves / shortest:.2f}倍" if (done and shortest) else "—"
    # 「分かれ道で聞いた回数」は一本道を数えない。長い行き止まりを往復しても増えないので、
    # 少ない＝賢い ではない（手数と合わせて見る）。
    mx = draw_metric(surf, x, my, "手数", str(moves), colour, w=105)
    mx = draw_metric(surf, mx, my, "最短比", ratio, w=115)
    mx = draw_metric(surf, mx, my, "分かれ道で聞いた回数", str(calls), w=165)
    mx = draw_metric(surf, mx, my, "推論の合計", f"{infer / 1000:.1f}s", w=115)
    draw_metric(surf, mx, my, "実時間", f"{wall / 1000:.1f}s", WIN if done else TEXT)

    # 直近の判断
    ly = my + 58
    head = "直近の判断"
    surf.blit(font(13).render(head, True, MUTED), (x, ly))
    if not done and moves >= runner.limit:
        note = font(13).render(f"{runner.limit}手で打ち切り（未到達）", True, (240, 140, 120))
        surf.blit(note, (rect.right - pad - note.get_width(), ly))
    elif done:
        note = font(13).render("ゴール", True, GOAL)
        surf.blit(note, (rect.right - pad - note.get_width(), ly))
    if detours:
        spans = [len(detour_span(runner.maze, d)) - 1 for d in detours]
        back = [n for n in spans if n > 0]
        msg = f"赤い丸：未踏の道があるのに通った道を選んだ {len(detours)}回"
        if back:
            msg += f"　赤い線：そこから戻るまでの遠回り {sum(back)}手"
        surf.blit(font(13).render(msg, True, DETOUR), (x, ly + 20))
    elif done:
        surf.blit(font(13).render("通った道を選んだ分かれ道は無し", True, MUTED), (x, ly + 20))
    elif err:
        surf.blit(font(15).render(err[:60], True, (240, 110, 110)), (x, ly + 20))
    elif last and last.probabilities:
        bx = x
        for name, p in sorted(last.probabilities.items(), key=lambda kv: -kv[1])[:4]:
            w = 108
            pygame.draw.rect(surf, (30, 36, 44), (bx, ly + 24, w, 8), border_radius=4)
            pygame.draw.rect(surf, colour if name == last.direction else DIM,
                             (bx, ly + 24, int(w * p), 8), border_radius=4)
            lab = font(13, name == last.direction).render(f"{name} {p:.2f}", True,
                                                          TEXT if name == last.direction else MUTED)
            surf.blit(lab, (bx, ly + 36))
            bx += w + 12
    elif last:
        surf.blit(font(15).render(last.reason or "コードで決定", True, DIM), (x, ly + 22))


def draw_header(surf, w, maze: Maze, seed: int, shortest: int) -> None:
    surf.blit(font(30, True).render("同じ迷路を、同時に解かせる", True, TEXT), (34, 26))
    sub = f"{maze.rows}×{maze.cols}　左上の S から右下の G へ　最短 {shortest} 手　／　見るのは実時間ではなく手数"
    surf.blit(font(15).render(sub, True, MUTED), (34, 64))


def draw_winner(surf, w, h, text: str) -> None:
    box = font(26, True).render(text, True, BG)
    pad = 22
    rect = pygame.Rect(0, 0, box.get_width() + pad * 2, box.get_height() + pad)
    rect.center = (w // 2, h - 42)
    pygame.draw.rect(surf, WIN, rect, border_radius=10)
    surf.blit(box, (rect.x + pad, rect.y + pad // 2))


def draw_frame(screen, W, H, rects, left, right, maze, seed, shortest) -> list:
    screen.fill(BG)
    draw_header(screen, W, maze, seed, shortest)
    draw_panel(screen, rects[0], left, JEV, JEV_SOFT, shortest)
    draw_panel(screen, rects[1], right, LAYA, LAYA_SOFT, shortest)

    a, b = left.stats, right.stats
    over = [r for r in (left, right) if r.stats.finished or r.stats.moves >= r.limit]
    if len(over) == 2:
        if a.finished and b.finished:
            if a.moves != b.moves:
                w = left if a.moves < b.moves else right
                draw_winner(screen, W, H,
                            f"手数で {w.player.name} の勝ち　{min(a.moves, b.moves)} 対 {max(a.moves, b.moves)}")
            else:
                draw_winner(screen, W, H, f"手数は同じ　{a.moves} 手")
        elif a.finished or b.finished:
            w = left if a.finished else right
            draw_winner(screen, W, H, f"{w.player.name} だけがゴール　{w.stats.moves} 手")
        else:
            draw_winner(screen, W, H, "どちらも未到達")
    return over


def replay(screen, W, H, rects, left, right, maze, seed, shortest, out: str, per: int) -> None:
    """走り終わった2人を、同じ手数ずつ進めて描き直す。

    実時間だと、Layaは1秒かからずにゴールしてしまい、どう歩いたかが見えない。
    ここで見せたいのは手数と遠回りなので、手数をそろえる。
    """
    end = max(left.stats.moves, right.stats.moves)
    ks = list(range(0, end, per)) + [end]
    for i, k in enumerate(ks):
        draw_frame(screen, W, H, rects, _RunnerAt(left, k), _RunnerAt(right, k), maze, seed, shortest)
        pygame.image.save(screen, os.path.join(out, f"{i:05d}.png"))
    print(f"{out} に {len(ks)} コマ書き出しました（1コマ {per} 手）")


# ---------------------------------------------------------------- 本体


def main() -> None:
    ap = argparse.ArgumentParser(description="JevとLayaに同じ迷路を解かせる")
    ap.add_argument("--size", type=int, default=31)
    ap.add_argument("--seed", type=int, default=7)
    # 既定は multilingual。公式ベンチの数字を出したのは typed-decisions だが、
    # この迷路では 60問中0問正解で、窓を渡すと壊れる（diagnose.py 参照）。
    # 盤面を実際に読んでいるのは multilingual だけだった。
    ap.add_argument("--laya", default="multilingual",
                    choices=["multilingual", "typed-decisions", "english"])
    ap.add_argument("--backend", default="mlx", choices=["mlx", "torch"])
    ap.add_argument("--limit", type=int, default=1200, help="打ち切る手数")
    ap.add_argument("--mock", action="store_true", help="APIもモデルも使わない")
    ap.add_argument("--shot", help="このPNGに書き出して終了（表示なし）")
    ap.add_argument("--shot-after", type=float, default=3.0, help="書き出しまでの秒数")
    ap.add_argument("--record", help="このフォルダに1コマずつPNGで書き出す（表示なし）")
    ap.add_argument("--fps", type=float, default=10, help="--record のコマ数（毎秒）")
    ap.add_argument("--replay", help="走り終わってから、手数をそろえてこのフォルダにPNGで描き直す（表示なし）")
    ap.add_argument("--moves-per-frame", type=int, default=4, help="--replay の1コマで進める手数")
    ap.add_argument("--hold", type=float, default=0.5, help="--record で、両方終わってから撮り続ける秒数")
    args = ap.parse_args()

    if args.shot or args.record or args.replay:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    for d in (args.record, args.replay):
        if d:
            os.makedirs(d, exist_ok=True)

    pygame.init()
    W, H = 1480, 940
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Jev vs Laya")
    clock = pygame.time.Clock()

    left_maze = Maze(rows=args.size, cols=args.size, seed=args.seed)
    right_maze = Maze(rows=args.size, cols=args.size, seed=args.seed)
    shortest = len(left_maze.shortest_path()) - 1

    if args.mock:
        p1 = MockPlayer("Jev", 238, 0.10)
        p1.badge = "mock / API想定"
        p2 = MockPlayer("Laya (multilingual)", 10, 0.45)
        p2.badge = "mock / ローカル想定"
    else:
        p1 = players.JevPlayer()
        p2 = players.LayaPlayer(args.laya, args.backend)

    left = Runner(p1, left_maze, args.limit)
    right = Runner(p2, right_maze, args.limit)
    left.start()
    right.start()

    pw = (W - 34 * 3) // 2
    rects = (pygame.Rect(34, 96, pw, H - 130), pygame.Rect(34 * 2 + pw, 96, pw, H - 130))

    running = True
    t0 = time.perf_counter()
    # 実時間のまま撮る。Layaが先に着いてJevがまだ歩いている、という差もそのまま映す
    frame, next_frame, ended_at = 0, 0.0, None
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False

        over = draw_frame(screen, W, H, rects, left, right, left_maze, args.seed, shortest)
        pygame.display.flip()

        if args.replay:
            if len(over) == 2:
                running = False
            clock.tick(30)
            continue

        if args.record:
            now = time.perf_counter() - t0
            if now >= next_frame:
                pygame.image.save(screen, os.path.join(args.record, f"{frame:05d}.png"))
                frame += 1
                next_frame += 1 / args.fps
            if len(over) == 2:
                ended_at = ended_at if ended_at is not None else now
                if now - ended_at >= args.hold:
                    print(f"{args.record} に {frame} コマ書き出しました")
                    running = False

        if args.shot and time.perf_counter() - t0 >= args.shot_after:
            pygame.image.save(screen, args.shot)
            print(f"{args.shot} に書き出しました")
            running = False

        clock.tick(30)

    if args.replay:
        replay(screen, W, H, rects, left, right, left_maze, args.seed, shortest,
               args.replay, args.moves_per_frame)

    for p in (p1, p2):
        p.close()
    pygame.quit()

    for r, label in ((left, p1.name), (right, p2.name)):
        s = r.stats
        print(f"{label:28} 手数 {s.moves:4}  最短比 {s.moves / shortest:.2f}倍  "
              f"呼出 {s.calls:3}  推論計 {s.infer_ms / 1000:6.1f}s  実時間 {s.wall_ms / 1000:6.1f}s  "
              f"{'ゴール' if s.finished else '未到達'}")


if __name__ == "__main__":
    main()
