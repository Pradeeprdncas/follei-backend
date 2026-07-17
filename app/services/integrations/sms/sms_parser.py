import re
from typing import Any


def parse_sms_body(body: str) -> dict[str, Any]:
    lines = [line.strip() for line in body.strip().split("\n") if line.strip()]
    data: dict[str, Any] = {}
    for line in lines:
        if ":" in line:
            key, _, value = line.partition(":")
            data[key.strip().lower().replace(" ", "_")] = value.strip()
    if not data:
        data["text"] = body
    return data


def extract_phone_numbers(text: str) -> list[str]:
    pattern = re.compile(r"\+?\d{10,15}")
    return pattern.findall(text)
