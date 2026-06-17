from app.config.database import SessionLocal
from app.repositories.chunk import ChunkRepository


def expand_neighbors(chunk_ids):

    db = SessionLocal()

    try:

        repo = ChunkRepository(db)

        expanded = {}

        for cid in chunk_ids:

            if not cid:
                continue

            chunk = repo.get_by_id(cid)

            if not chunk:
                continue

            neighbors = [
                chunk.id,
                chunk.parent_chunk_id,
                chunk.prev_chunk_id,
                chunk.next_chunk_id,
            ]

            for neighbor_id in neighbors:

                if not neighbor_id:
                    continue

                neighbor = repo.get_by_id(neighbor_id)

                if not neighbor:
                    continue

                expanded[str(neighbor.id)] = {
                    "chunk_id": str(neighbor.id),
                    "score": 0,
                    "text": neighbor.text,
                    "page": neighbor.page,
                    "heading": neighbor.heading,
                    "chunk_index": neighbor.chunk_index
                }

        return list(expanded.values())

    finally:
        db.close()