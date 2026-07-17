"""CSV chunker — chunk by row groups with repeated headers.

Never splits mid-row. Headers repeated in every chunk for self-contained
context. Configurable rows per chunk (default 50).
"""
import csv
import io
from pathlib import Path
from loguru import logger


def chunk_csv(
    file_path: str,
    rows_per_chunk: int = 50,
    repeat_headers: bool = True,
) -> list[dict]:
    """Chunk a CSV file into row-group chunks with repeated headers.

    Args:
        file_path: Path to CSV file.
        rows_per_chunk: Number of data rows per chunk (default 50).
        repeat_headers: Whether to include headers in every chunk (default True).

    Returns:
        list of dicts with keys: chunk_type, type, headers, rows, row_range,
                                 content (CSV-formatted string)
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning("CSV file not found: {}", file_path)
        return []

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            all_rows = list(reader)
    except Exception as e:
        logger.error("Failed to read CSV {}: {}", file_path, e)
        return []

    if not all_rows:
        return []

    headers = all_rows[0]
    data_rows = all_rows[1:]

    if not data_rows:
        return [{
            "chunk_type": "csv",
            "type": "csv",
            "headers": headers,
            "rows": [],
            "row_range": (0, 0),
            "content": ",".join(headers) if headers else "",
        }]

    chunks: list[dict] = []
    for start in range(0, len(data_rows), rows_per_chunk):
        end = min(start + rows_per_chunk, len(data_rows))
        batch = data_rows[start:end]

        output = io.StringIO()
        writer = csv.writer(output)
        if repeat_headers:
            writer.writerow(headers)
        writer.writerows(batch)
        csv_string = output.getvalue().strip()

        chunks.append({
            "chunk_type": "csv",
            "type": "csv",
            "headers": headers,
            "rows": batch,
            "row_range": (start + 1, end),
            "content": csv_string,
        })

    logger.info("CSVChunker: {} chunks from {} ({} rows, {} per chunk)",
                len(chunks), path.name, len(data_rows), rows_per_chunk)
    return chunks


def chunk_csv_text(
    text: str,
    rows_per_chunk: int = 50,
    repeat_headers: bool = True,
) -> list[dict]:
    """Chunk CSV text content (no file). Useful for in-memory CSV strings."""
    reader = csv.reader(io.StringIO(text))
    all_rows = list(reader)

    if not all_rows:
        return []

    headers = all_rows[0]
    data_rows = all_rows[1:]

    chunks: list[dict] = []
    for start in range(0, len(data_rows), rows_per_chunk):
        end = min(start + rows_per_chunk, len(data_rows))
        batch = data_rows[start:end]

        output = io.StringIO()
        writer = csv.writer(output)
        if repeat_headers:
            writer.writerow(headers)
        writer.writerows(batch)
        csv_string = output.getvalue().strip()

        chunks.append({
            "chunk_type": "csv",
            "type": "csv",
            "headers": headers,
            "rows": batch,
            "row_range": (start + 1, end),
            "content": csv_string,
        })

    return chunks
