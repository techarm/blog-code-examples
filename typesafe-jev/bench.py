#!/usr/bin/env python3
"""大阪からJevを叩いてレイテンシを測る。

公式のベンチは「西海岸にある自分たちのノートPCから」実行したもの、と
公式ブログが自分で書いている。日本から叩いたら何msなのかを測る。

測るのは2つ:
  1. 質問1つ vs 3つ同時 — 「並列評価なので質問を増やしても劣化しない」の検証
  2. stateが英語 vs 日本語 — 公式が「CJKは精度が落ちる」と書いている件の確認

質問文と選択肢は常に英語に固定する。変えるのは state の言語だけ。
両方いっぺんに変えると、何が効いたのか分からなくなる。

使い方:
    python bench.py --n 40
    python bench.py --n 40 --lang en
"""

import argparse
import json
import statistics
import time
from datetime import datetime, timezone

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

STATE_EN = {
    "ticket": (
        "Hi, I've been trying to connect my Stripe account for 3 days and it keeps "
        "failing. I'm losing sales. Please help ASAP."
    )
}

STATE_JA = {
    "ticket": (
        "3日前からStripeアカウントの連携が失敗し続けています。"
        "そのあいだ決済が通らず売上が落ちています。至急なんとかしてください。"
    )
}

# 質問は常に英語。stateの言語だけを変えて比べる。
CHOICE_ONLY = {
    "department": Choice(
        instructions={
            "question": "Which team should handle this ticket?",
            "inspect": "`ticket`",
        },
        criteria={
            "billing": "Payment or subscription problems",
            "technical": "Bugs or integration failures",
            "sales": "Pricing or account questions",
            "other": "A request that fits none of the above",
        },
    ),
}

ALL_THREE = {
    **CHOICE_ONLY,
    "frustration": Score(
        instructions={
            "question": "How frustrated does the customer appear?",
            "inspect": "`ticket`",
            "focus": "Judge expressed frustration, not how serious the issue is.",
        },
        criteria=[
            {"what": "Calm and matter-of-fact"},
            {"what": "Frustrated but civil"},
            {"what": "Very angry, using strong language"},
        ],
    ),
    "is_urgent": Noul(
        instructions={
            "question": "Is the customer under time pressure right now?",
            "inspect": "`ticket`",
        },
    ),
}


def percentile(values: list[float], p: float) -> float:
    ordered = sorted(values)
    k = (len(ordered) - 1) * p
    lo, hi = int(k), min(int(k) + 1, len(ordered) - 1)
    return ordered[lo] + (ordered[hi] - ordered[lo]) * (k - lo)


def run(client, state: dict, questions: dict, n: int) -> list[float]:
    latencies = []
    for i in range(n):
        started = time.perf_counter()
        client.system_one(state=state, questions=questions)
        latencies.append((time.perf_counter() - started) * 1000)
        print(f"\r  {i + 1}/{n}", end="", flush=True)
    print()
    return latencies


def summarize(label: str, latencies: list[float]) -> dict:
    row = {
        "label": label,
        "n": len(latencies),
        "min": round(min(latencies)),
        "p50": round(statistics.median(latencies)),
        "p95": round(percentile(latencies, 0.95)),
        "max": round(max(latencies)),
    }
    print(
        f"{label:<28} n={row['n']:<4} "
        f"min {row['min']:>4}ms  p50 {row['p50']:>4}ms  "
        f"p95 {row['p95']:>4}ms  max {row['max']:>4}ms"
    )
    return row


def main() -> None:
    parser = argparse.ArgumentParser(description="Jevのレイテンシ計測")
    parser.add_argument("--n", type=int, default=50, help="各条件の試行回数")
    parser.add_argument("--lang", choices=["ja", "en", "both"], default="both")
    parser.add_argument("--out", default="bench-result.json", help="結果の保存先")
    args = parser.parse_args()

    states = []
    if args.lang in ("en", "both"):
        states.append(("state=英語", STATE_EN))
    if args.lang in ("ja", "both"):
        states.append(("state=日本語", STATE_JA))

    results = []
    with TypeSafeClient() as client:
        for lang_label, state in states:
            for q_label, questions in (("質問1つ", CHOICE_ONLY), ("質問3つ同時", ALL_THREE)):
                label = f"{lang_label} / {q_label}"
                print(f"計測中: {label}")
                results.append(summarize(label, run(client, state, questions, args.n)))

    payload = {
        "measured_at": datetime.now(timezone.utc).isoformat(),
        "location": "Osaka, Japan",
        "notes": [
            "公式ベンチは西海岸のノートPCから実行、と公式ブログに記載あり",
            "質問文と選択肢は常に英語。変えたのは state の言語だけ",
            "公式ドキュメント（concepts/state）に CJK は精度が落ちると明記あり",
        ],
        "results": results,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    print(f"\n{args.out} に保存しました")


if __name__ == "__main__":
    main()
