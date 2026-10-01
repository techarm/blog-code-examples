"""2つのデモ（迷路・Snake）で共有する見た目。

記事に並べたときに同じ画面に見えてほしいので、色と文字と部品はここに集める。
"""

from __future__ import annotations

import os

import pygame

# ---------------------------------------------------------------- 配色

BG = (13, 17, 23)
PANEL = (22, 27, 34)
PANEL_EDGE = (48, 54, 61)
BOARD = (8, 11, 16)
TEXT = (230, 237, 243)
MUTED = (125, 138, 153)
DIM = (72, 82, 95)
RULE = (38, 45, 56)

JEV = (88, 166, 255)
JEV_SOFT = (33, 61, 97)
LAYA = (255, 166, 87)
LAYA_SOFT = (92, 60, 26)
GOOD = (87, 217, 142)
WARN = (255, 214, 102)
BAD = (240, 110, 110)

# ---------------------------------------------------------------- 文字

# 画面の文言は日本語。pygame の既定フォントには日本語が無く、全部豆腐になる。
_JP = (
    "/System/Library/Fonts/ヒラギノ角ゴシック W3.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
    "/System/Library/Fonts/AppleSDGothicNeo.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
)
# 数字は等幅のほうが、毎フレーム変わっても横に暴れない。
_MONO = (
    "/System/Library/Fonts/SFNSMono.ttf",
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Supplemental/Andale Mono.ttf",
)

_cache: dict[tuple, pygame.font.Font] = {}


def _first(paths) -> str | None:
    for p in paths:
        if os.path.exists(p):
            return p
    return None


def font(size: int, bold: bool = False, mono: bool = False) -> pygame.font.Font:
    key = (size, bold, mono)
    if key not in _cache:
        path = _first(_MONO) if mono else _first(_JP)
        f = pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
        if bold and path:
            f.set_bold(True)
        _cache[key] = f
    return _cache[key]


def text(surf, s, pos, size=15, colour=TEXT, bold=False, mono=False, right=None):
    img = font(size, bold, mono).render(s, True, colour)
    x = (right - img.get_width()) if right is not None else pos[0]
    surf.blit(img, (x, pos[1]))
    return img.get_width()


# ---------------------------------------------------------------- 部品


def panel(surf, rect) -> None:
    pygame.draw.rect(surf, PANEL, rect, border_radius=14)
    pygame.draw.rect(surf, PANEL_EDGE, rect, width=1, border_radius=14)


def badge(surf, rect_right, y, label, colour, soft) -> None:
    img = font(13).render(label, True, colour)
    w = img.get_width() + 18
    pygame.draw.rect(surf, soft, (rect_right - w, y, w, 25), border_radius=6)
    surf.blit(img, (rect_right - w + 9, y + 5))


def metric(surf, x, y, label, value, colour=TEXT, unit="", size=27) -> None:
    text(surf, label, (x, y), 12, MUTED)
    w = text(surf, value, (x, y + 16), size, colour, bold=True, mono=True)
    if unit:
        text(surf, unit, (x + w + 3, y + 16 + size - 14), 12, MUTED)


def bars(surf, x, y, probs: dict[str, float], picked: str | None, colour,
         width=150, labels: dict[str, str] | None = None) -> None:
    """4方向の確率。モデルが確定する前に、どこへ何を配ったか。"""
    labels = labels or {}
    for i, name in enumerate(("up", "down", "left", "right")):
        p = probs.get(name)
        ry = y + i * 21
        text(surf, labels.get(name, name), (x, ry), 13, TEXT if name == picked else MUTED)
        bx = x + 34
        pygame.draw.rect(surf, (30, 36, 44), (bx, ry + 5, width, 7), border_radius=4)
        if p is not None:
            pygame.draw.rect(surf, colour if name == picked else DIM,
                             (bx, ry + 5, max(int(width * p), 1), 7), border_radius=4)
        text(surf, f"{p:.2f}" if p is not None else "—", (0, ry), 13,
             TEXT if name == picked else DIM, mono=True, right=bx + width + 44)


def rule(surf, x, y, w) -> None:
    pygame.draw.line(surf, RULE, (x, y), (x + w, y))
