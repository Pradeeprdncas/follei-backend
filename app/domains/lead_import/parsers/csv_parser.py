"""CSV file parser using stdlib csv and pandas."""

import csv
import io
from pathlib import Path
from app.domains.lead_import.parsers.base import BaseParser, ExtractedDocument


class CSVParser(BaseParser):
    """Parse CSV files — detects delimiter, extracts text and tabular data."""

    async def parse(self, file_path: str) -> ExtractedDocument:
        path = Path(file_path)
        raw = path.read_bytes()

        # Detect encoding and delimiter
        try:
            content = raw.decode("utf-8-sig")
        except UnicodeDecodeError:
            content = raw.decode("latin-1")

        dialect = self._detect_dialect(content)
        reader = csv.reader(io.StringIO(content), dialect)
        rows = [row for row in reader if row]

        if not rows:
            return ExtractedDocument(metadata={"filename": path.name, "rows": 0, "delimiter": dialect.delimiter})

        header = rows[0]
        data = rows[1:]

        text_parts = [", ".join(header)]
        text_parts.extend(", ".join(row) for row in data)
        text = "\n".join(text_parts)

        doc = ExtractedDocument(
            text=text,
            tables=[rows],
            metadata={
                "filename": path.name,
                "rows": len(data),
                "columns": len(header),
                "delimiter": dialect.delimiter,
                "column_names": header,
            },
            pages=1,
        )
        return doc

    @staticmethod
    def _detect_dialect(content: str) -> csv.Dialect:
        try:
            return csv.Sniffer().sniff(content[:4096])
        except csv.Error:
            return csv.excel()
