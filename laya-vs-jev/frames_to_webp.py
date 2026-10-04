#!/usr/bin/env python3
"""race.py --record で書き出したPNGを、アニメーションWebPにまとめる。

    python race.py --record frames
    python frames_to_webp.py frames race.webp

GIFだと31×31の迷路が数百手動くだけで数MBになるので、WebPにしている。
最後のコマ（結果の画面）は、そこで止まって見えるように長めに表示する。
"""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("frames", help="PNGが入ったフォルダ")
    ap.add_argument("out", help="書き出すWebP")
    ap.add_argument("--fps", type=float, default=10, help="race.py --record と同じ値にする")
    ap.add_argument("--last", type=float, default=4.0, help="最後のコマを表示する秒数")
    ap.add_argument("--width", type=int, default=0, help="縮める幅（0なら元のまま）")
    ap.add_argument("--quality", type=int, default=70)
    args = ap.parse_args()

    paths = sorted(Path(args.frames).glob("*.png"))
    if not paths:
        raise SystemExit(f"{args.frames} にPNGがありません")
    images = []
    for p in paths:
        im = Image.open(p).convert("RGB")
        if args.width and im.width > args.width:
            im = im.resize((args.width, round(im.height * args.width / im.width)), Image.LANCZOS)
        images.append(im)

    step = round(1000 / args.fps)
    durations = [step] * len(images)
    durations[-1] = round(args.last * 1000)
    images[0].save(args.out, save_all=True, append_images=images[1:], duration=durations,
                   loop=0, quality=args.quality, method=6)
    size = Path(args.out).stat().st_size
    print(f"{args.out}  {len(images)}コマ  {size / 1024:.0f}KB")


if __name__ == "__main__":
    main()
