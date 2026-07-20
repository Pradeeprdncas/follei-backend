import re


def looks_like_table(text: str) -> bool:
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip()
    ]

    if len(lines) < 3:
        return False

    # Delimited tables survive many PDF/DOCX extractors as literal pipes rather
    # than aligned whitespace.  Two data/header rows are sufficient evidence;
    # prose documents using a single pipe should still take the layout path.
    pipe_rows = sum(1 for line in lines if line.count("|") >= 2)
    # A policy/handbook may contain a few tables. Treat it as table-oriented
    # only when rows dominate the document, otherwise hierarchy chunking keeps
    # the surrounding headings and prose retrievable.
    if pipe_rows >= 2 and pipe_rows / len(lines) >= 0.60:
        return True

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
