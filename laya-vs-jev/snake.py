#!/usr/bin/env python3
"""JevとLayaに同じSnakeを同時に遊ばせる。

    python snake.py                  # Jev vs Laya（multilingual）
    python snake.py --mock           # APIもモデルも使わず見た目だけ確認
    python snake.py --shot out.png --shot-after 20

迷路との違いは、**1手のミスが即死**すること。遠回りで誤魔化せないので、
判断の質がそのままスコアになる。

画面に出している「安全補正」は、**モデルが自殺手を選んだのをコードが止めた回数**。
スコアだけ見ていると、コードがどれだけ尻拭いしたか分からない。
"""

from __future__ import annotations

import argparse
import os
import random
import statistics
import threading
import time
from dataclasses import dataclass, field

import pygame

import snake_core as sc
import ui


@dataclass
class Shot:
    direction: str = ""
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None
    latency_ms: float = 0.0
    corrected: bool = False   # モデルの手が自殺手で、コードが差し替えた
    model_said: str = ""


@dataclass
class Tally:
    decisions: int = 0
    corrections: int = 0
    deaths: int = 0
    best: int = 0
    apples: int = 0
    latencies: list[float] = field(default_factory=list)
    started: float = field(default_factory=time.perf_counter)

    @property
    def p50(self) -> float:
        return statistics.median(self.latencies) if self.latencies else 0.0

    @property
    def per_sec(self) -> float:
        el = time.perf_counter() - self.started
        return self.decisions / el if el > 0 else 0.0


# ---------------------------------------------------------------- 走者


class Seat:
    def __init__(self, player, rows, cols, seed) -> None:
        self.player = player
        self.rows, self.cols, self.seed = rows, cols, seed
        self.game = sc.Snake(rows=rows, cols=cols, seed=seed)
        self.tally = Tally()
        self.last = Shot()
        self.error: str | None = None
        self.lock = threading.Lock()
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self.thread.start()

    def _run(self) -> None:
        try:
            while not self.stop.is_set():
                g = self.game
                safe = g.safe_options()
                if not safe:                       # 詰み。どう動いても死ぬ
                    self._die()
                    continue
                shot = self.player.decide(g)
                picked = shot.direction
                if g.fatal(picked):                # 自殺手はコードが止める
                    shot.model_said = picked
                    shot.corrected = True
                    picked = max(safe, key=g.open_space)
                    shot.direction = picked
                with self.lock:
                    self.tally.decisions += 1
                    self.tally.latencies.append(shot.latency_ms)
                    if shot.corrected:
                        self.tally.corrections += 1
                    self.last = shot
                before = g.score
                g.step(picked)
                with self.lock:
                    if g.score > before:
                        self.tally.apples += 1
                    if not g.alive:
                        self._die(locked=True)
        except Exception as exc:
            with self.lock:
                self.error = f"{type(exc).__name__}: {exc}"

    def _die(self, locked: bool = False) -> None:
        def body():
            self.tally.deaths += 1
            self.tally.best = max(self.tally.best, self.game.score)
            self.seed_next()
        if locked:
            body()
        else:
            with self.lock:
                body()

    def seed_next(self) -> None:
        self.seed += 1
        self.game = sc.Snake(rows=self.rows, cols=self.cols, seed=self.seed)


# ---------------------------------------------------------------- 打ち手


class MockPlayer:
    name = "Mock"
    model = "—"
    badge = "mock"

    def __init__(self, ms: float, suicidal: float) -> None:
        self.ms, self.suicidal = ms, suicidal
        self.rng = random.Random(1)

    def close(self) -> None:
        pass

    def decide(self, g: sc.Snake) -> Shot:
        time.sleep(self.ms / 1000)
        opts = g.options()
        safe = g.safe_options()
        ar, ac = g.apple
        def score(d):
            r, c = g.cell_after(d)
            return (-(abs(r - ar) + abs(c - ac)), g.open_space(d))
        best = max(safe, key=score) if safe else opts[0]
        pick = self.rng.choice(opts) if self.rng.random() < self.suicidal else best
        p = {d: self.rng.random() for d in opts}
        tot = sum(p.values())
        return Shot(pick, {k: v / tot for k, v in p.items()}, max(p.values()) / tot, self.ms)


class JevPlayer:
    name = "JEV"
    model = "TypeSafe · jev-1.13.0"
    badge = "リモート / API"

    def __init__(self, trap_mode: str = "none") -> None:
        from typesafe_sdk import TypeSafeClient
        self.client = TypeSafeClient()
        self.trap_mode = trap_mode

    def close(self) -> None:
        self.client.close()

    def decide(self, g: sc.Snake) -> Shot:
        from typesafe_sdk import Choice
        t = time.perf_counter()
        r = self.client.system_one(
            state=sc.build_state(g, self.trap_mode),
            questions={
                "direction": Choice(
                    instructions={
                        "question": sc.QUESTION,
                        "inspect": "`directions`",
                        "focus": sc.focus_for(self.trap_mode),
                    },
                    criteria=sc.build_criteria(g),
                )
            },
        )
        a = r.answers["direction"]
        return Shot(a.choice, dict(a.probabilities), a.confidence,
                    (time.perf_counter() - t) * 1000)


class LayaPlayer:
    badge = "ローカル / M1 Ultra"

    def __init__(self, checkpoint: str = "multilingual", trap_mode: str = "none",
                 backend: str = "mlx") -> None:
        # backend="mlx" は非公式の移植版（mizorewww/laya-mlx）。
        # 実際の局面200件で本家と答えが 200/200 一致し、確率の差は最大0.0027。
        # p50 は 21.3ms（本家 PyTorch/MPS）に対して 9.97ms。M1 Ultra での実測。
        self.trap_mode = trap_mode
        self.backend = backend
        if backend == "mlx":
            import laya_mlx as backend_mod
        else:
            import laya as backend_mod
        self.name = "LAYA"
        self.model = f"convaiinnovations/laya · {checkpoint} · {backend}"
        self.badge = f"ローカル / M1 Ultra · {'MLX' if backend == 'mlx' else 'PyTorch'}"
        self.agent = backend_mod.load(
            "convaiinnovations/laya",
            subfolder=None if checkpoint == "english" else checkpoint,
        )

    def close(self) -> None:
        pass

    def decide(self, g: sc.Snake) -> Shot:
        t = time.perf_counter()
        r = self.agent.predict(
            sc.build_state(g, self.trap_mode),
            {"direction": {"type": "choice",
                           "instructions": f"{sc.QUESTION} {sc.focus_for(self.trap_mode)}",
                           "criteria": sc.build_criteria(g)}},
        )
        a = r["answers"]["direction"]
        return Shot(a["choice"], dict(a.get("probabilities", {})), a.get("confidence"),
                    (time.perf_counter() - t) * 1000)


# ---------------------------------------------------------------- 描画

JP = {"up": "上", "down": "下", "left": "左", "right": "右"}


def draw_board(surf, rect, g: sc.Snake, colour, soft) -> None:
    cell = min(rect.width // g.cols, rect.height // g.rows)
    w, h = cell * g.cols, cell * g.rows
    ox = rect.x + (rect.width - w) // 2
    oy = rect.y
    pygame.draw.rect(surf, ui.BOARD, (ox, oy, w, h), border_radius=6)

    for i, (r, c) in enumerate(g.body):
        t = 1 - i / max(len(g.body), 1)
        col = tuple(int(soft[k] + (colour[k] - soft[k]) * (0.35 + 0.65 * t)) for k in range(3))
        pygame.draw.rect(surf, col, (ox + c * cell, oy + r * cell, cell - 1, cell - 1),
                         border_radius=3 if i else 5)
    ar, ac = g.apple
    pygame.draw.circle(surf, ui.WARN,
                       (ox + ac * cell + cell // 2, oy + ar * cell + cell // 2),
                       max(cell // 3, 3))
    if not g.alive:
        ui.text(surf, f"GAME OVER — {g.cause}", (ox + 10, oy + h - 24), 14, ui.BAD, mono=True)
    return oy + h


def draw_seat(surf, rect, seat: Seat, colour, soft) -> None:
    ui.panel(surf, rect)
    pad = 24
    x = rect.x + pad
    right = rect.right - pad
    y = rect.y + pad

    ui.text(surf, seat.player.name, (x, y), 30, colour, bold=True)
    ui.badge(surf, right, y + 3, seat.player.badge, ui.TEXT, soft)
    ui.text(surf, seat.player.model, (x, y + 38), 13, ui.MUTED, mono=True)
    ui.rule(surf, x, y + 62, right - x)

    with seat.lock:
        g, t, last, err = seat.game, seat.tally, seat.last, seat.error
        score, length = g.score, len(g.body)
        dec, corr, deaths, best = t.decisions, t.corrections, t.deaths, t.apples
        p50, per_sec = t.p50, t.per_sec
        lat = last.latency_ms

    sy = y + 78
    ui.text(surf, f"{score:03d}", (x, sy), 34, colour, bold=True, mono=True)
    ui.text(surf, "スコア", (x + 72, sy + 16), 13, ui.MUTED)
    ui.text(surf, "長さ", (x + 126, sy + 16), 13, ui.MUTED)
    ui.text(surf, f"{length:03d}", (x + 158, sy + 16), 13, ui.MUTED, mono=True)
    ui.text(surf, "全速で推論", (0, sy + 16), 13, ui.MUTED, right=right)

    board_bottom = draw_board(surf, pygame.Rect(x, sy + 48, right - x, 392), g, colour, soft)

    my = board_bottom + 20
    col = (right - x) // 4
    ui.metric(surf, x + col * 0, my, "直近の推論", f"{lat:.1f}", colour, "ms")
    ui.metric(surf, x + col * 1, my, "P50 レイテンシ", f"{p50:.1f}", ui.TEXT, "ms")
    ui.metric(surf, x + col * 2, my, "判断 / 秒", f"{per_sec:.1f}", ui.TEXT)
    ui.metric(surf, x + col * 3, my, "総判断数", f"{dec}", ui.TEXT)

    ry = my + 62
    ui.rule(surf, x, ry - 8, right - x)
    ui.bars(surf, x, ry, last.probabilities, last.direction, colour, 150, JP)

    # 右側は、スコアに出てこない数字
    rx = x + 300
    rate = corr / dec * 100 if dec else 0
    ui.metric(surf, rx, ry - 4, "安全補正（コードが止めた自殺手）",
              f"{corr}", ui.BAD if corr else ui.GOOD, f"／ {rate:.1f}%", size=24)
    ui.metric(surf, rx, ry + 44, "死んだ回数", f"{deaths}", ui.TEXT, size=24)
    ui.metric(surf, rx + 110, ry + 44, "食べた数", f"{best}", ui.GOOD, size=24)

    if err:
        ui.text(surf, err[:70], (x, rect.bottom - 34), 13, ui.BAD)
    elif last.corrected:
        ui.text(surf, f"モデルは {JP.get(last.model_said, last.model_said)} を選んだ（即死）",
                (x, rect.bottom - 34), 13, ui.BAD)


# ---------------------------------------------------------------- 本体


def main() -> None:
    ap = argparse.ArgumentParser(description="JevとLayaに同じSnakeを遊ばせる")
    ap.add_argument("--rows", type=int, default=18)
    ap.add_argument("--cols", type=int, default=24)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--laya", default="multilingual",
                    choices=["multilingual", "typed-decisions", "english"])
    ap.add_argument("--backend", default="mlx", choices=["mlx", "torch"],
                    help="Laya の実行経路。mlx は非公式の移植版（本家と答えが一致、2.1倍速い）")
    ap.add_argument("--trap", default="none", choices=["none", "as_blocked", "trap_word"],
                    help="袋小路をstateに書くか。既定は書かない（理由は snake_core.py）")
    ap.add_argument("--mock", action="store_true")
    ap.add_argument("--shot")
    ap.add_argument("--shot-after", type=float, default=15.0)
    args = ap.parse_args()

    if args.shot:
        os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

    pygame.init()
    W, H = 1480, 862
    screen = pygame.display.set_mode((W, H))
    pygame.display.set_caption("Jev vs Laya — Snake")
    clock = pygame.time.Clock()

    if args.mock:
        p1 = MockPlayer(238, 0.06)
        p1.name, p1.model, p1.badge = "JEV", "mock · jev想定", "リモート / API"
        p2 = MockPlayer(32, 0.18)
        p2.name, p2.model, p2.badge = "LAYA", "mock · laya想定", "ローカル / M1 Ultra"
    else:
        p1 = JevPlayer(args.trap)
        p2 = LayaPlayer(args.laya, args.trap, args.backend)

    left = Seat(p1, args.rows, args.cols, args.seed)
    right = Seat(p2, args.rows, args.cols, args.seed)
    left.start()
    right.start()

    pw = (W - 34 * 3) // 2
    rects = (pygame.Rect(34, 86, pw, H - 120), pygame.Rect(34 * 2 + pw, 86, pw, H - 120))

    t0 = time.perf_counter()
    running = True
    while running:
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT or (ev.type == pygame.KEYDOWN and ev.key == pygame.K_ESCAPE):
                running = False

        screen.fill(ui.BG)
        ui.text(screen, "同じSnakeを、同時に遊ばせる", (34, 24), 29, ui.TEXT, bold=True)
        ui.text(screen, f"{args.rows}×{args.cols}　1手のミスが即死　"
                        f"／　見るのはスコアだけでなく「安全補正」",
                (34, 58), 14, ui.MUTED)

        draw_seat(screen, rects[0], left, ui.JEV, ui.JEV_SOFT)
        draw_seat(screen, rects[1], right, ui.LAYA, ui.LAYA_SOFT)
        pygame.display.flip()

        if args.shot and time.perf_counter() - t0 >= args.shot_after:
            pygame.image.save(screen, args.shot)
            print(f"{args.shot} に書き出しました")
            running = False
        clock.tick(30)

    for s in (left, right):
        s.stop.set()
    for p in (p1, p2):
        p.close()
    pygame.quit()

    for s in (left, right):
        t = s.tally
        print(f"{s.player.name:6} 判断 {t.decisions:5}  食べた {t.apples:4}  死 {t.deaths:3}  "
              f"安全補正 {t.corrections:4} ({t.corrections / max(t.decisions,1) * 100:.1f}%)  "
              f"p50 {t.p50:6.1f}ms  {t.per_sec:5.1f}判断/秒")


if __name__ == "__main__":
    main()
