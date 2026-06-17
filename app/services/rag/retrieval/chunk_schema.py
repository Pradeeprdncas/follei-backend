def normalize_chunk(chunk):

    if "payload" in chunk:

        return {
            "chunk_id": chunk["chunk_id"],
            "text": chunk["payload"].get("text", ""),
            "page": chunk["payload"].get("page"),
            "heading": chunk["payload"].get("heading"),
            "chunk_index": chunk["payload"].get("chunk_index")
        }

    return {
        "chunk_id": chunk.get("chunk_id"),
        "text": chunk.get("text", ""),
        "page": chunk.get("page"),
        "heading": chunk.get("heading"),
        "chunk_index": chunk.get("chunk_index")
    }