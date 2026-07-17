"""Excel file parser for .xlsx and .xls using openpyxl and pandas."""

from pathlib import Path
import pandas as pd
from app.domains.lead_import.parsers.base import BaseParser, ExtractedDocument


class ExcelParser(BaseParser):
    """Parse Excel workbooks — extracts all sheets as text + tables."""

    async def parse(self, file_path: str) -> ExtractedDocument:
        path = Path(file_path)
        ext = path.suffix.lower()

        if ext == ".xls":
            engine = "xlrd"
        else:
            engine = "openpyxl"

        excel_file = pd.ExcelFile(file_path, engine=engine)
        sheet_names = excel_file.sheet_names
        doc = ExtractedDocument(metadata={"filename": path.name, "sheets": len(sheet_names)})
        total_rows = 0

        for sheet_name in sheet_names:
            df = excel_file.parse(sheet_name)

            if df.empty:
                continue

            buf = [f"--- Sheet: {sheet_name} ---"]
            buf.append("\t".join(str(c) for c in df.columns))
            for _, row in df.iterrows():
                buf.append("\t".join(str(v) if pd.notna(v) else "" for v in row))
            sheet_text = "\n".join(buf)

            header = [str(c) for c in df.columns]
            table = [header]
            for _, row in df.iterrows():
                table.append([str(v) if pd.notna(v) else "" for v in row])

            total_rows += len(df)
            sheet_doc = ExtractedDocument(
                text=sheet_text,
                tables=[table],
                metadata={
                    "sheet": sheet_name,
                    "rows": len(df),
                    "columns": len(df.columns),
                    "column_names": list(df.columns),
                },
                pages=1,
            )
            doc.merge(sheet_doc)

        doc.metadata["total_rows"] = total_rows
        return doc
