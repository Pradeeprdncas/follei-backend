"""Email/call chunking preserving speaker and timestamp boundaries."""
from uuid import uuid4
import re

_TURN = re.compile(r"^(?:\[(?P<timestamp>[^\]]+)\]\s*)?(?P<speaker>[A-Za-z][\w .-]{0,40})?:?\s*(?P<body>.+)$")

class TurnAwareChunker:
    name = "turn_aware"

    def chunk(self, pages: list[dict], *, metadata: dict | None = None) -> list[dict]:
        result = []
        for page in pages:
            for line in [x.strip() for x in page.get("text", "").splitlines() if x.strip()]:
                match = _TURN.match(line)
                speaker = match.group("speaker").strip() if match and match.group("speaker") else None
                timestamp = match.group("timestamp") if match else page.get("timestamp")
                body = match.group("body") if match else line
                result.append({
                    "chunk_id": str(uuid4()), "parent_chunk_id": None,
                    "prev_chunk_id": result[-1]["chunk_id"] if result else None,
                    "next_chunk_id": None, "page": page.get("page", 0),
                    "heading": page.get("heading"),
                    "section_path": [page["heading"]] if page.get("heading") else [],
                    "chunk_index": len(result), "chunk_type": "speaker_turn",
                    "speaker": speaker, "timestamp": timestamp,
                    "word_count": len(body.split()), "text": body,
                    "approval_status": "draft", "sensitivity": (metadata or {}).get("sensitivity", "internal"),
                    "source_type": (metadata or {}).get("source_type", "conversation"),
                    "confidence": float((metadata or {}).get("confidence", 0.0)),
                })
                if len(result) > 1:
                    result[-2]["next_chunk_id"] = result[-1]["chunk_id"]
        return result
