import re


def looks_like_table(text: str) -> bool:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if len(lines) < 3:
        return False

    score = 0

    for line in lines:
        columns = re.split(r"\s{2,}", line)

        if len(columns) >= 3:
            score += 1

    return score >= 3


def looks_like_code(text: str) -> bool:

    keywords = [
        "def ",
        "class ",
        "import ",
        "return ",
        "public ",
        "private ",
        "function ",
        "{",
        "}",
    ]

    count = sum(
        kw in text
        for kw in keywords
    )

    return count >= 2


def looks_like_list(text: str) -> bool:

    lines = text.splitlines()

    bullet_count = 0

    for line in lines:

        if re.match(
            r"^\s*[-*•]\s+",
            line
        ):
            bullet_count += 1

    return bullet_count >= 3