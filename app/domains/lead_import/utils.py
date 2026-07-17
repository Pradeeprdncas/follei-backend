"""Utility helpers for the Lead Import domain."""

import os
import re
import uuid
from pathlib import Path
from typing import BinaryIO

from app.domains.lead_import.constants import FileType


def detect_file_type(filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    return FileType.from_extension(ext)


def guess_mimetype(filename: str) -> str:
    ext = Path(filename).suffix.lstrip(".").lower()
    mime_map = {
        "csv": "text/csv",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "xls": "application/vnd.ms-excel",
        "pdf": "application/pdf",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "txt": "text/plain",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
    }
    return mime_map.get(ext, "application/octet-stream")


def save_upload(file: BinaryIO, filename: str, upload_dir: str) -> str:
    os.makedirs(upload_dir, exist_ok=True)
    unique_name = f"{uuid.uuid4().hex}_{filename}"
    file_path = os.path.join(upload_dir, unique_name)
    with open(file_path, "wb") as f:
        f.write(file.read())
    return file_path


# ── AI Extraction Utilities ─────────────────────────────────────────────


def split_full_name(full_name: str) -> tuple[str | None, str | None]:
    if not full_name or not isinstance(full_name, str):
        return None, None
    parts = full_name.strip().split(None, 1)
    if len(parts) == 1:
        return parts[0], None
    return parts[0], parts[1]


def normalize_email(email: str) -> str:
    if not email or not isinstance(email, str):
        return str(email) if email else ""
    return email.strip().lower()


def normalize_phone(phone: str) -> str:
    if not phone or not isinstance(phone, (str, int)):
        return str(phone) if phone else ""
    cleaned = re.sub(r"[^\d]", "", str(phone))
    if not cleaned:
        return str(phone)
    if cleaned.startswith("+"):
        return cleaned
    if cleaned.startswith("00"):
        cleaned = cleaned[2:]
    if cleaned.startswith("0"):
        cleaned = cleaned[1:]
    return "+" + cleaned


def normalize_website(website: str) -> str:
    if not website or not isinstance(website, str):
        return str(website) if website else ""
    w = website.strip()
    if not w:
        return w
    if not w.startswith(("http://", "https://")):
        w = "https://" + w
    return w.rstrip("/")


def calculate_confidence(lead: dict) -> float:
    score = 0.5
    primary = ["first_name", "last_name", "email", "phone", "company"]
    secondary = ["website", "linkedin", "designation", "city", "country"]
    for field in primary:
        val = lead.get(field)
        if val and isinstance(val, str) and val.strip():
            score += 0.1
    for field in secondary:
        val = lead.get(field)
        if val and isinstance(val, str) and val.strip():
            score += 0.05
    return round(min(score, 1.0), 2)
