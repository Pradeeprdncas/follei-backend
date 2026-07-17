"""Table chunker — detects table regions via PyMuPDF layout analysis.

Each table is serialized as markdown and stored as a single chunk.
Row integrity is preserved — never splits mid-table.
Output is compatible with the hierarchy_chunk format for seamless merging.
"""
import uuid
import pymupdf as fitz
from loguru import logger


def chunk_table_regions(pdf_path: str) -> list[dict]:
    """Extract table regions from a PDF and return as markdown chunks.

    Uses PyMuPDF page layout to detect table-like blocks (columns of text
    at consistent x-positions, aligned rows). Each detected table region
    is serialized to markdown and returned as one chunk.

    Returns:
        list of dicts with keys: chunk_type, type, content, page, row_count, columns
    """
    doc = fitz.open(pdf_path)
    chunks: list[dict] = []

    for page_number in range(len(doc)):
        page = doc[page_number]
        blocks = page.get_text("dict")["blocks"]

        table_blocks = _detect_table_blocks(blocks)
        for table_data in table_blocks:
            md_table = _blocks_to_markdown(table_data)
            if md_table:
                chunk_id = str(uuid.uuid4())
                chunks.append({
                    "chunk_type": "table",
                    "type": "table",
                    "chunk_id": chunk_id,
                    "text": md_table,
                    "content": md_table,
                    "page": page_number + 1,
                    "heading": None,
                    "section_path": [],
                    "word_count": len(md_table.split()),
                    "parent_chunk_id": None,
                    "prev_chunk_id": None,
                    "next_chunk_id": None,
                    "row_count": len(table_data.get("rows", [])),
                    "columns": table_data.get("headers", []),
                })

    doc.close()
    logger.info("TableChunker: {} table chunks from {}", len(chunks), pdf_path)
    return chunks


def _detect_table_blocks(blocks: list[dict]) -> list[dict]:
    """Detect table-like block clusters from PyMuPDF page blocks.

    Strict heuristic — requires:
    - Each row has 3+ distinct text cells (spans or lines at different x)
    - Consistent column count across rows (±1)
    - Rows are vertically close (within 30 units)
    Rejects blocks with a single long text span (prose paragraphs).
    """
    text_blocks = [b for b in blocks if "lines" in b]
    if len(text_blocks) < 3:
        return []

    tables: list[dict] = []
    candidate_rows: list[dict] = []
    current_table_rect = None

    for block in text_blocks:
        bbox = block["bbox"]
        x0, y0, x1, y1 = bbox
        row_span_count = _count_spans(block)
        row_text = _extract_row_text(block)

        # True table rows have multiple distinct cells, not one long text
        is_table_row = (
            row_span_count >= 2
            and len(row_text) >= 2
            and (x1 - x0) > 50
            and (y1 - y0) < 80
        )

        if is_table_row:
            if current_table_rect and abs(y0 - current_table_rect[3]) > 30:
                if _is_coherent_table(candidate_rows):
                    tables.append(_finalize_table(candidate_rows))
                candidate_rows = []
            candidate_rows.append({"texts": row_text, "bbox": bbox})
            current_table_rect = bbox
        else:
            if _is_coherent_table(candidate_rows):
                tables.append(_finalize_table(candidate_rows))
            candidate_rows = []
            current_table_rect = None

    if _is_coherent_table(candidate_rows):
        tables.append(_finalize_table(candidate_rows))

    return tables


def _count_spans(block: dict) -> int:
    """Count distinct text spans (cells) in a block."""
    spans = set()
    for line in block.get("lines", []):
        x_positions = set()
        for span in line.get("spans", []):
            x_positions.add(round(span.get("bbox", [0])[0], 0))
        spans.update(x_positions)
    return len(spans)


def _is_coherent_table(rows: list[dict]) -> bool:
    """Check that candidate rows form a coherent table (consistent col count)."""
    if len(rows) < 2:
        return False
    col_counts = [len(r["texts"]) for r in rows]
    if any(c < 2 for c in col_counts):
        return False
    return max(col_counts) - min(col_counts) <= 1


def _extract_row_text(block: dict) -> list[str]:
    """Extract cell texts from a PyMuPDF block.

    Merges spans within the same x-region into cell text.
    """
    cells: list[tuple[float, str]] = []
    for line in block.get("lines", []):
        for span in line.get("spans", []):
            x = span.get("bbox", [0])[0]
            text = span["text"].strip()
            if text:
                cells.append((x, text))

    # Group spans at similar x positions
    cells.sort(key=lambda t: t[0])
    if not cells:
        return []

    grouped = []
    current_x = cells[0][0]
    current_texts = [cells[0][1]]
    for x, text in cells[1:]:
        if abs(x - current_x) < 10:
            current_texts.append(text)
        else:
            grouped.append(" ".join(current_texts))
            current_x = x
            current_texts = [text]
    grouped.append(" ".join(current_texts))

    return grouped


def _finalize_table(rows: list[dict]) -> dict:
    """Build a table dict from collected rows."""
    if not rows:
        return {"headers": [], "rows": []}
    first_row_texts = rows[0]["texts"]
    data_rows = []
    for row in rows[1:]:
        data_rows.append(row["texts"])
    return {
        "headers": first_row_texts,
        "rows": data_rows,
    }


def _blocks_to_markdown(table_data: dict) -> str:
    """Serialize a table to markdown format."""
    headers = table_data.get("headers", [])
    rows = table_data.get("rows", [])

    if not headers and not rows:
        return ""

    col_count = max(len(headers), max((len(r) for r in rows), default=0))
    if col_count == 0:
        return ""

    def _pad(cells: list[str]) -> list[str]:
        return cells + [""] * (col_count - len(cells))

    header = _pad(headers)
    separator = ["---"] * col_count
    data = [_pad(r) for r in rows]

    md = "| " + " | ".join(header) + " |\n"
    md += "| " + " | ".join(separator) + " |\n"
    for row in data:
        md += "| " + " | ".join(row) + " |\n"

    return md
