#!/usr/bin/env python3
"""state が日本語だと判定が変わるかを測る。

公式ドキュメント（concepts/state）にこう書いてある:

  Jev's primary training language is English; other languages, including
  CJK scripts, are accepted but currently have lower accuracy.

「落ちる」と書いてあるが、どれくらい落ちるかは書いていない。日本語で使えるのか
知りたいので測る。

やり方:
  同じ内容のサポート問い合わせを英語版と日本語版で用意し、まったく同じ質問を
  投げて、答えが一致するかを見る。正解ラベルは要らない。食い違えば、
  内容ではなく言語が結果を動かしたことになる。

  質問文と選択肢は常に英語。変えるのは state の言語だけ。

使い方:
    python lang_check.py
    python lang_check.py --repeat 3   # ばらつきを見る
"""

import argparse
import statistics

from typesafe_sdk import Choice, Noul, Score, TypeSafeClient

# 対になる問い合わせ。内容は同じ、言語だけ違う。
# 実在の問い合わせではなく、この検証のために書いたもの。
PAIRS = [
    (
        "I was charged twice for order A-104. Please refund the duplicate.",
        "注文A-104で二重に請求されています。重複分を返金してください。",
    ),
    (
        "My package was supposed to arrive on Monday and it is still not here.",
        "荷物は月曜に届く予定でしたが、まだ届いていません。",
    ),
    (
        "How much does the team plan cost if we have 12 people?",
        "12人で使う場合、チームプランはいくらになりますか。",
    ),
    (
        "The API returns 500 on every request since this morning. Everything is down.",
        "今朝からAPIが全リクエストで500を返します。全部止まっています。",
    ),
    (
        "The shoes are the wrong size. I would like to exchange them for a 27cm.",
        "靴のサイズが違いました。27cmに交換したいです。",
    ),
    (
        "Just wanted to say the new dashboard is great. No issue, thanks.",
        "新しいダッシュボード、とても良いです。特に問題はありません。ありがとう。",
    ),
    (
        "This is the third time I am writing. Nobody has replied. I want a human.",
        "これで3回目です。誰からも返事がありません。人間の担当者をお願いします。",
    ),
    (
        "Please confirm your account by replying with your password to avoid suspension.",
        "アカウント停止を避けるため、パスワードを返信して確認してください。",
    ),
    (
        "Can you send me the invoice for last month as a PDF?",
        "先月分の請求書をPDFで送ってもらえますか。",
    ),
    (
        "We are evaluating your product against a competitor. Can we get a demo?",
        "御社の製品を他社と比較検討しています。デモをお願いできますか。",
    ),
    (
        "My card was declined but the money left my account. Where is it?",
        "カードが拒否されたのに口座からお金が引かれています。どこにありますか。",
    ),
    (
        "Login works on Chrome but fails on Safari with a blank screen.",
        "Chromeではログインできますが、Safariだと真っ白になって失敗します。",
    ),
    (
        "Hi Kenji, are we still on for lunch on Thursday?",
        "けんじさん、木曜のランチはまだ大丈夫ですか。",
    ),
    (
        "Our production database is corrupted and customers cannot check out.",
        "本番データベースが壊れていて、お客様が決済できません。",
    ),
    (
        "I would like to cancel my subscription before the next billing date.",
        "次回の請求日より前に、サブスクリプションを解約したいです。",
    ),
    (
        "You have won a prize. Click this link and enter your card details to claim it.",
        "賞品が当選しました。このリンクからカード情報を入力して受け取ってください。",
    ),
]

# 質問文まで日本語にした版。公式は質問も英語を推奨しているので、
# 「state の言語」と「質問の言語」のどちらが効くのかを切り分けるために使う。
QUESTIONS_JA = {
    "category": Choice(
        instructions={
            "question": "この問い合わせは何についてのものか",
            "inspect": "`message`",
        },
        criteria={
            "billing": "請求、支払い、課金、返金",
            "incident": "障害、停止、不具合",
            "shipping": "配送状況、遅延、誤品や破損",
            "sales": "価格、プラン、製品の比較検討",
            "personal": "サポート依頼ではない個人的な連絡",
            "other": "上のどれにも当てはまらないもの",
        },
    ),
    "urgency": Score(
        instructions={
            "question": "どれくらい早く対応が必要か",
            "inspect": "`message`",
        },
        criteria=[
            {"what": "期限はまったくない"},
            {"what": "今週中でよい"},
            {"what": "今日中に対応が要る"},
            {"what": "放置すると実害が出続ける"},
        ],
    ),
    "is_phishing": Noul(
        instructions={
            "question": "この問い合わせはフィッシングや詐欺か",
            "inspect": "`message`",
        },
    ),
}

QUESTIONS = {
    "category": Choice(
        instructions={
            "question": "What is this message about?",
            "inspect": "`message`",
        },
        criteria={
            "billing": "An invoice, a payment, a charge, or a refund",
            "incident": "An outage, a failure, or a bug",
            "shipping": "Delivery status, delays, wrong or damaged items",
            "sales": "Pricing, plans, or evaluating the product",
            "personal": "A personal message, not a support request",
            "other": "Something that fits none of the above",
        },
    ),
    "urgency": Score(
        instructions={
            "question": "How soon does this need a response?",
            "inspect": "`message`",
        },
        criteria=[
            {"what": "No deadline at all"},
            {"what": "Some time this week is fine"},
            {"what": "Needs handling today"},
            {"what": "Real damage accrues while it waits"},
        ],
    ),
    "is_phishing": Noul(
        instructions={
            "question": "Is this message a phishing or fraud attempt?",
            "inspect": "`message`",
        },
    ),
}


def ask(client, text: str, questions=None) -> dict:
    r = client.system_one(state={"message": text}, questions=questions or QUESTIONS)
    return {
        "category": r.answers["category"].choice,
        "category_conf": r.answers["category"].confidence,
        "urgency": r.answers["urgency"].score,
        "urgency_conf": r.answers["urgency"].confidence,
        "phishing": r.answers["is_phishing"].noul,
        "tokens": r.usage.input_tokens,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="state の言語で判定が変わるかを測る")
    parser.add_argument("--repeat", type=int, default=1, help="各ペアを何回ずつ測るか")
    parser.add_argument(
        "--jp-questions",
        action="store_true",
        help="質問文と選択肢も日本語にする（公式は英語を推奨）",
    )
    args = parser.parse_args()

    questions = QUESTIONS_JA if args.jp_questions else QUESTIONS
    print(f"質問文の言語: {'日本語' if args.jp_questions else '英語'}")

    cat_match = 0
    total = 0
    urgency_gap = []
    phishing_gap = []
    conf_en = []
    conf_ja = []
    tok_en = []
    tok_ja = []
    mismatches = []

    with TypeSafeClient() as client:
        for _ in range(args.repeat):
            for en, ja in PAIRS:
                a, b = ask(client, en, questions), ask(client, ja, questions)
                total += 1
                if a["category"] == b["category"]:
                    cat_match += 1
                else:
                    mismatches.append((en[:52], a["category"], b["category"]))
                urgency_gap.append(abs(a["urgency"] - b["urgency"]))
                phishing_gap.append(abs(a["phishing"] - b["phishing"]))
                conf_en.append(a["category_conf"])
                conf_ja.append(b["category_conf"])
                tok_en.append(a["tokens"])
                tok_ja.append(b["tokens"])

    print(f"対になる問い合わせ {len(PAIRS)} 件 × {args.repeat} 回 = {total} 組")
    print()
    print(f"Choice（種類）が一致        : {cat_match}/{total}  ({cat_match/total*100:.0f}%)")
    print(f"Score（緊急度）の差 中央値  : {statistics.median(urgency_gap):.3f} / 3")
    print(f"Score の差 最大              : {max(urgency_gap):.3f}")
    print(f"Noul（詐欺）の差 中央値     : {statistics.median(phishing_gap):.3f}")
    print(f"Noul の差 最大               : {max(phishing_gap):.3f}")
    print()
    print(f"confidence 平均  英語 {statistics.mean(conf_en):.3f} / 日本語 {statistics.mean(conf_ja):.3f}")
    print(f"入力トークン平均 英語 {statistics.mean(tok_en):.0f} / 日本語 {statistics.mean(tok_ja):.0f}")

    if mismatches:
        print()
        print("食い違ったもの:")
        for text, en_a, ja_a in mismatches:
            print(f"  「{text}...」")
            print(f"      英語 → {en_a} / 日本語 → {ja_a}")


if __name__ == "__main__":
    main()
