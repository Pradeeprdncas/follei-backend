from app.repositories.chunk import ChunkRepository
from app.repositories.document import DocumentRepository
from app.config.database import SessionLocal


def build_context(chunk_ids):

    if not chunk_ids:
        return ""

    db = SessionLocal()

    try:

        chunk_repo = ChunkRepository(db)
        doc_repo = DocumentRepository(db)

        chunks = chunk_repo.get_by_ids(chunk_ids)

        if not chunks:
            return ""

        chunks.sort(
            key=lambda c: (
                str(c.document_id),
                c.chunk_index
            )
        )

        document_cache = {}

        sections = []

        for chunk in chunks:

            if chunk.document_id not in document_cache:

                document_cache[
                    chunk.document_id
                ] = doc_repo.get_by_id(
                    chunk.document_id
                )

            doc = document_cache[
                chunk.document_id
            ]

            document_name = (
                doc.filename
                if doc
                else "Unknown"
            )

            section_path = ""

            if chunk.section_path:

                if isinstance(
                    chunk.section_path,
                    list
                ):
                    section_path = (
                        " > ".join(
                            chunk.section_path
                        )
                    )
                else:
                    section_path = str(
                        chunk.section_path
                    )

            sections.append(
                f"""
DOCUMENT:
{document_name}

PAGE:
{chunk.page}

SECTION:
{section_path}

TYPE:
{chunk.chunk_type}

CONTENT:
{chunk.text}
"""
            )

        return "\n\n====================\n\n".join(
            sections
        )

    finally:
        db.close()