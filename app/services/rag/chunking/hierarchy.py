from uuid import uuid4
from app.services.rag.chunking.adaptive import adaptive_chunk


def hierarchy_chunk(pages):

    chunks = []

    previous_chunk = None

    for page in pages:

        page_number = page["page"]

        text = page["text"]

        heading = page.get("heading")

        adaptive_chunks = adaptive_chunk(text)

        parent_id = str(uuid4())

        for idx, chunk in enumerate(adaptive_chunks):

            chunk_id = str(uuid4())

            chunks.append({
                "chunk_id": chunk_id,
                "parent_chunk_id": parent_id,
                "prev_chunk_id": previous_chunk,
                "next_chunk_id": None,

                "page": page_number,

                "heading": heading,

                "section_path": [heading] if heading else [],

                "chunk_index": idx,

                "chunk_type": chunk["chunk_type"],

                "word_count": len(chunk["text"].split()),

                "text": chunk["text"]
            })

            if len(chunks) > 1:
                chunks[-2]["next_chunk_id"] = chunk_id

            previous_chunk = chunk_id

    return chunks