#!/usr/bin/env python3
"""質問の数を増やしたらレイテンシがどう変わるかを測る。

公式ドキュメントはこう書いている:

  Questions are evaluated in parallel. Adding questions barely changes
  the response time.

そして公式のデモ（typesafe-race）は、約27個の質問を1回にまとめて投げ、
LLM との差を 0.114秒 対 8.566秒 として見せている。

つまりあのデモは「まとめて投げたから速い」条件。本当に平らなのかを、
同じ27個まで伸ばして確かめる。

使い方:
    python scale_check.py
    python scale_check.py --n 30
"""

import argparse
import statistics
import time

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

TICKET = (
    "Our checkout has been returning 500 errors since this morning. "
    "Customers cannot pay. We are also seeing duplicate charges on some "
    "cards. This is the third time this quarter. We need this fixed today "
    "or we will move to another provider."
)


def noul(q: str) -> Noul:
    return Noul(instructions={"question": q, "inspect": "`ticket`"})


def score(q: str, levels: list[str]) -> Score:
    return Score(
        instructions={"question": q, "inspect": "`ticket`"},
        criteria=[{"what": level} for level in levels],
    )


def choice(q: str, criteria: dict[str, str]) -> Choice:
    return Choice(instructions={"question": q, "inspect": "`ticket`"}, criteria=criteria)


# 公式デモと同じくらいの粒度で27問。前から順に切って使う。
BANK: list[tuple[str, object]] = [
    ("revenue_impacted", noul("Is revenue currently impacted?")),
    ("integration_issue", noul("Is there an integration issue?")),
    ("security_concern", noul("Is a security concern present?")),
    ("duplicate_charge", noul("Is a duplicate charge reported?")),
    ("human_needed", noul("Is human attention needed?")),
    ("feature_request", noul("Is this an immediate feature request?")),
    ("churn_risk", noul("Is there a credible churn risk?")),
    ("production_down", noul("Is a production capability down?")),
    ("data_exposed", noul("Is customer data exposed?")),
    ("server_error", noul("Is a server error reported?")),
    ("repeated_failure", noul("Are these repeated production failures?")),
    ("threatening", noul("Is the language personally threatening?")),
    ("deadline_stated", noul("Is a concrete deadline stated?")),
    ("partner_risk", noul("Is a partner launch endangered?")),
    ("refund_wanted", noul("Is the customer asking for a refund?")),
    ("churn_level", score("How likely is this customer to churn?",
                          ["unlikely", "possible", "likely", "imminent"])),
    ("scope_certainty", score("How certain is the scope of the incident?",
                              ["unknown", "partial", "clear"])),
    ("security_risk", score("How severe is the security risk?",
                            ["none", "low", "serious"])),
    ("financial_impact", score("How large is the financial impact?",
                               ["none", "small", "large"])),
    ("tech_specificity", score("How technically specific is the report?",
                               ["vague", "some detail", "precise"])),
    ("resolution_complexity", score("How complex is the resolution?",
                                    ["trivial", "moderate", "hard"])),
    ("urgency", score("How soon must this be answered?",
                      ["no deadline", "this week", "today", "right now"])),
    ("department", choice("Which team should handle this?",
                          {"billing": "Charges and payments",
                           "technical": "Bugs and outages",
                           "sales": "Pricing",
                           "other": "None of the above"})),
    ("impact", choice("What is the business impact?",
                      {"none": "No impact",
                       "degraded": "Degraded service",
                       "outage": "Full outage"})),
    ("scope", choice("What is the incident scope?",
                     {"single_account": "One account",
                      "subset": "Some customers",
                      "all": "Everyone"})),
    ("account_health", choice("What is the account health status?",
                              {"healthy": "Fine",
                               "watch": "Needs watching",
                               "at_risk": "At risk"})),
    ("resolution", choice("What resolution is requested?",
                          {"restore_service": "Fix it",
                           "refund": "Money back",
                           "explanation": "Explain what happened",
                           "other": "None of the above"})),
]

STEPS = (1, 3, 9, 18, 27)
PRICE_PER_MTOK = 0.042  # 公式の入力単価


def main() -> None:
    parser = argparse.ArgumentParser(description="質問数とレイテンシの関係を測る")
    parser.add_argument("--n", type=int, default=15, help="各条件の試行回数")
    args = parser.parse_args()

    print(f"{'質問数':>6} {'p50':>9} {'min':>7} {'max':>7} {'入力tok':>9} {'1問比':>8} {'1回のコスト':>12}")
    base = None

    with TypeSafeClient() as client:
        for k in STEPS:
            questions = dict(BANK[:k])
            latencies = []
            tokens = 0
            for _ in range(args.n):
                started = time.perf_counter()
                r = client.system_one(state={"ticket": TICKET}, questions=questions)
                latencies.append((time.perf_counter() - started) * 1000)
                tokens = r.usage.input_tokens

            p50 = statistics.median(latencies)
            if base is None:
                base = p50
            cost = tokens / 1_000_000 * PRICE_PER_MTOK
            print(
                f"{k:>6} {p50:>8.0f}ms {min(latencies):>6.0f} {max(latencies):>6.0f} "
                f"{tokens:>9,} {p50 / base:>7.2f}倍 {cost:>12.6f}"
            )


if __name__ == "__main__":
    main()
