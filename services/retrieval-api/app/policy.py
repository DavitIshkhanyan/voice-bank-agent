from __future__ import annotations

import re

TOPIC_KEYWORDS = {
    "credits": [
        "վարկ",
        "հիփոթեք",
    ],
    "deposits": [
        "ավանդ",
    ],
    "branch_locations": [
        "մասնաճյուղ",
        "հասցե",
    ],
}

ALLOWED_TOPICS = set(TOPIC_KEYWORDS)


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def classify_topic(question: str) -> str | None:
    q = normalize(question)
    matches = []
    for topic, keywords in TOPIC_KEYWORDS.items():
        if any(k in q for k in keywords):
            matches.append(topic)
    if len(matches) != 1:
        return None
    return matches[0]


def refusal_out_of_scope() -> str:
    return (
        "Կարող եմ պատասխանել միայն բանկային վարկերի, ավանդների և մասնաճյուղերի գտնվելու վայրի մասին "
        "հարցերին՝ հիմնվելով պաշտոնական կայքերի տվյալների վրա։"
    )


def refusal_no_grounding() -> str:
    return (
        "Չեմ գտել բավարար տվյալ պաշտոնական աղբյուրներում ձեր հարցին վստահելի պատասխան տալու համար։ "
        "Խնդրում եմ վերաձևակերպեք հարցը կամ նշեք բանկը։"
    )

