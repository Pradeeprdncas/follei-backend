"""EML and MSG text extraction."""
from pathlib import Path
from email import policy
from email.parser import BytesParser

_MAX_ATTACHMENT_BYTES = 2 * 1024 * 1024
_TEXT_ATTACHMENT_TYPES = {"text/plain", "text/csv", "application/json"}
_TEXT_ATTACHMENT_EXTENSIONS = {".txt", ".csv", ".json"}


def extract_email_text(file_path: str | Path) -> list[dict]:
    path = Path(file_path)
    if path.suffix.lower() == ".msg":
        import extract_msg
        message = extract_msg.Message(str(path))
        subject, sender, body = message.subject or "Email", message.sender or "", message.body or ""
        msg_attachments = []
        for attachment in message.attachments:
            filename = getattr(attachment, "longFilename", None) or getattr(attachment, "shortFilename", None) or "unnamed"
            data = getattr(attachment, "data", b"") or b""
            if isinstance(data, str):
                data = data.encode("utf-8")
            if Path(filename).suffix.lower() in _TEXT_ATTACHMENT_EXTENSIONS and len(data) <= _MAX_ATTACHMENT_BYTES:
                msg_attachments.append(f"Attachment {filename}:\n{data.decode('utf-8', errors='replace')}")
        body = "\n\n".join([body, *msg_attachments])
        message.close()
    else:
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
        subject, sender = message.get("subject") or "Email", message.get("from") or ""
        plain = message.get_body(preferencelist=("plain",))
        body = plain.get_content() if plain else ""
        attachments = []
        for part in message.iter_attachments():
            payload = part.get_payload(decode=True) or b""
            if len(payload) > _MAX_ATTACHMENT_BYTES or part.get_content_type() not in _TEXT_ATTACHMENT_TYPES:
                continue
            attachments.append(f"Attachment {part.get_filename() or 'unnamed'}:\n{payload.decode(part.get_content_charset() or 'utf-8', errors='replace')}")
        body = "\n\n".join([body, *attachments])
    text = "\n".join(filter(None, [f"Subject: {subject}", f"From: {sender}", body.strip()]))
    return [{"page": 1, "heading": subject, "text": text}] if text else []
