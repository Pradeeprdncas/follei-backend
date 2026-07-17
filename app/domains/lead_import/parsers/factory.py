"""Parser factory — maps file types to parser implementations."""

from app.domains.lead_import.constants import FileType
from app.domains.lead_import.parsers.base import BaseParser
from app.domains.lead_import.parsers.csv_parser import CSVParser
from app.domains.lead_import.parsers.excel_parser import ExcelParser
from app.domains.lead_import.parsers.pdf_parser import PDFParser
from app.domains.lead_import.parsers.docx_parser import DOCXParser
from app.domains.lead_import.parsers.image_parser import ImageParser
from app.domains.lead_import.parsers.text_parser import TextParser


class ParserFactory:
    """Registry that returns the correct parser for a given file type."""

    _registry: dict[str, type[BaseParser]] = {
        FileType.CSV: CSVParser,
        FileType.XLSX: ExcelParser,
        FileType.XLS: ExcelParser,
        FileType.PDF: PDFParser,
        FileType.DOCX: DOCXParser,
        FileType.TXT: TextParser,
        FileType.PNG: ImageParser,
        FileType.JPG: ImageParser,
        FileType.JPEG: ImageParser,
    }

    @classmethod
    def get_parser(cls, file_type: str) -> BaseParser:
        parser_cls = cls._registry.get(file_type)
        if not parser_cls:
            raise ValueError(f"No parser registered for file type: {file_type}")
        return parser_cls()

    @classmethod
    def register(cls, file_type: str, parser_cls: type[BaseParser]) -> None:
        cls._registry[file_type] = parser_cls
