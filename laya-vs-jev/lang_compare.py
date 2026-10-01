#!/usr/bin/env python3
"""1本目の日本語テストを、Layaでもやる。

1本目（typesafe-jev/lang_check.py）と同じ16対の問い合わせ、同じ質問を使う。
同じ内容を英語と日本語で書いた2通に、まったく同じ質問を投げて、答えが揃うかを見る。

1本目の結論:
  Jevは、データ（state）が日本語でも判定は揃う（32/32）。
  落ちたのは質問文を日本語にしたとき（28/32）。

ここでは Laya でも同じことが言えるかを見る。加えて:

- 英日で揃っていても、両方間違っていれば意味がない。**同じ入力でJevと同じ答えか**も数える
- Snakeで、Layaは否定文に出てくる語に引き寄せられた（"Never choose trap" で trap を選ぶ）。
  personal の説明 "A personal message, not a support request" の "support request" に
  釣られていないかを見るため、否定を外した版でも測る

使い方:
    python lang_compare.py                # Laya の3チェックポイント
    python lang_compare.py --jev          # Jev の答えとの一致も数える（API 128回）
"""

from __future__ import annotations

import argparse
import copy
import statistics
import sys
import time
from pathlib import Path

# 1本目のデータと質問をそのまま使う（書き写さない）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "typesafe-jev"))
import lang_check as one  # noqa: E402

PAIRS = one.PAIRS

# ---- 質問の変種 ------------------------------------------------------------

# 否定を外した personal。ほかは1本目のまま。
PERSONAL_EN = "A personal message between friends or colleagues"
PERSONAL_JA = "友人や同僚どうしの個人的な連絡"


def variant(questions, no_negation: bool, ja: bool):
    q = copy.deepcopy(questions)
    if no_negation:
        q["category"].criteria["personal"] = PERSONAL_JA if ja else PERSONAL_EN
    return q


def to_laya(questions) -> dict:
    """SDKの型付き質問を、Laya の辞書に移す。中身は変えない。"""
    out = {}
    for key, q in questions.items():
        instr = q.instructions["question"] if isinstance(q.instructions, dict) else q.instructions
        crit = getattr(q, "criteria", None)
        kind = type(q).__name__.lower()
        d = {"type": kind, "instructions": instr}
        if kind == "choice":
            d["criteria"] = dict(crit)
        elif kind == "score":
            d["criteria"] = [c["what"] for c in crit]
        out[key] = d
    return out


CONDITIONS = [
    ("質問=英語", one.QUESTIONS, False, False),
    ("質問=日本語", one.QUESTIONS_JA, False, True),
    ("質問=英語・否定なし", one.QUESTIONS, True, False),
    ("質問=日本語・否定なし", one.QUESTIONS_JA, True, True),
]


# ---- 実行 -----------------------------------------------------------------


def run_laya(agent, laya_q, repeat: int):
    """各テキストの答え（2回目以降は1回目と同じかどうかも見る）"""
    answers = []  # [(en_ans, ja_ans)] per pair, first run
    deterministic = True
    lat = []
    for rep in range(repeat):
        for i, (en, ja) in enumerate(PAIRS):
            pair = []
            for text in (en, ja):
                t = time.perf_counter()
                r = agent.predict({"message": text}, laya_q)
                lat.append((time.perf_counter() - t) * 1000)
                a = r["answers"]
                pair.append(
                    {
                        "category": a["category"]["choice"],
                        "urgency": a["urgency"]["score"],
                        "phishing": a["is_phishing"]["noul"],
                    }
                )
            if rep == 0:
                answers.append(tuple(pair))
            elif tuple(pair) != answers[i]:
                deterministic = False
    return answers, deterministic, statistics.median(lat)


def run_jev(client, questions):
    out = []
    for en, ja in PAIRS:
        pair = []
        for text in (en, ja):
            r = client.system_one(state={"message": text}, questions=questions)
            pair.append(r.answers["category"].choice)
        out.append(tuple(pair))
    return out


def summarize(answers, repeat: int):
    match = sum(1 for a, b in answers if a["category"] == b["category"])
    urg = statistics.median(abs(a["urgency"] - b["urgency"]) for a, b in answers)
    phi = statistics.median(abs(a["phishing"] - b["phishing"]) for a, b in answers)
    n = len(answers)
    # 決定的なので、2回やっても同じ。1本目の「32組」にそろえて倍で書く
    return f"{match * repeat}/{n * repeat}", match / n, urg, phi


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repeat", type=int, default=2)
    ap.add_argument("--jev", action="store_true")
    ap.add_argument("--checkpoints", default="multilingual,english,typed-decisions")
    args = ap.parse_args()

    jev_answers = {}
    if args.jev:
        from typesafe_sdk import TypeSafeClient

        with TypeSafeClient() as client:
            for label, base, neg, ja in CONDITIONS:
                jev_answers[label] = run_jev(client, variant(base, neg, ja))
        print("=== Jev（参考）===")
        for label, ans in jev_answers.items():
            m = sum(1 for a, b in ans if a == b)
            print(f"  {label:20} 英日一致 {m}/16")
        print()

    import laya

    for ck in args.checkpoints.split(","):
        ck = ck.strip()
        agent = laya.load("convaiinnovations/laya", subfolder=None if ck == "english" else ck)
        print(f"=== Laya / {ck} ===")
        for label, base, neg, ja in CONDITIONS:
            q = to_laya(variant(base, neg, ja))
            answers, det, p50 = run_laya(agent, q, args.repeat)
            frac, _, urg, phi = summarize(answers, args.repeat)
            line = (
                f"  {label:20} 英日一致 {frac:>6}  Score差 {urg:.3f}  Noul差 {phi:.3f}  "
                f"p50 {p50:5.1f}ms  {'決定的' if det else '★毎回変わる'}"
            )
            if jev_answers:
                ref = jev_answers[label]
                agree = sum(
                    (answers[i][0]["category"] == ref[i][0]) + (answers[i][1]["category"] == ref[i][1])
                    for i in range(len(PAIRS))
                )
                line += f"  Jevと同じ答え {agree}/32"
            print(line)
        print()


if __name__ == "__main__":
    main()
