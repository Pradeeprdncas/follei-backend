"""Constants and enumerations for the Lead Import domain."""


class FileType:
    """Supported file type constants."""
    CSV = "csv"
    XLSX = "xlsx"
    XLS = "xls"
    PDF = "pdf"
    DOCX = "docx"
    TXT = "txt"
    PNG = "png"
    JPG = "jpg"
    JPEG = "jpeg"

    ALL = {CSV, XLSX, XLS, PDF, DOCX, TXT, PNG, JPG, JPEG}

    @classmethod
    def from_extension(cls, ext: str) -> str:
        ext = ext.lower().lstrip(".")
        if ext in {"jpg", "jpeg"}:
            return cls.JPEG
        if ext in cls.ALL:
            return ext
        raise ValueError(f"Unsupported file extension: {ext}")

    @classmethod
    def is_image(cls, file_type: str) -> bool:
        return file_type in {cls.PNG, cls.JPG, cls.JPEG}

    @classmethod
    def is_document(cls, file_type: str) -> bool:
        return file_type in {cls.PDF, cls.DOCX, cls.TXT}

    @classmethod
    def is_spreadsheet(cls, file_type: str) -> bool:
        return file_type in {cls.CSV, cls.XLSX, cls.XLS}

    @classmethod
    def needs_ocr(cls, file_type: str) -> bool:
        return cls.is_image(file_type)


class ImportStatus:
    """Status values for LeadImportJob lifecycle."""
    PENDING = "pending"
    PROCESSING = "processing"
    PARSING = "parsing"
    EXTRACTING = "extracting"
    ENRICHING = "enriching"
    INTELLIGENCE = "intelligence"
    CORRECTING = "correcting"
    VALIDATING = "validating"
    REVIEWING = "reviewing"
    PREVIEW_READY = "preview_ready"
    COMMITTED = "committed"
    FAILED = "failed"

    ACTIVE = {PENDING, PROCESSING, PARSING, EXTRACTING, ENRICHING, INTELLIGENCE, CORRECTING, VALIDATING, REVIEWING}
    TERMINAL = {PREVIEW_READY, COMMITTED, FAILED}


class DocumentType:
    """Document type classification constants."""
    EMPLOYEE_DIRECTORY = "employee_directory"
    BUSINESS_DIRECTORY = "business_directory"
    CRM_EXPORT = "crm_export"
    SALES_LEADS = "sales_leads"
    CUSTOMER_LIST = "customer_list"
    INVOICE = "invoice"
    EVENT_REGISTRATION = "event_registration"
    CONFERENCE_ATTENDEES = "conference_attendees"
    VENDOR_LIST = "vendor_list"
    MARKETING_LIST = "marketing_list"
    PURCHASE_RECORDS = "purchase_records"
    COMPANY_REPORT = "company_report"
    GOVERNMENT_DATA = "government_data"
    PHONE_BOOK = "phone_book"
    IMPORT_LIST = "import_list"
    RESUME = "resume"
    TENDER = "tender"
    UNKNOWN = "unknown"

    ALL = {
        EMPLOYEE_DIRECTORY, BUSINESS_DIRECTORY, CRM_EXPORT, SALES_LEADS,
        CUSTOMER_LIST, INVOICE, EVENT_REGISTRATION, CONFERENCE_ATTENDEES,
        VENDOR_LIST, MARKETING_LIST, PURCHASE_RECORDS, COMPANY_REPORT,
        GOVERNMENT_DATA, PHONE_BOOK, IMPORT_LIST, RESUME, TENDER, UNKNOWN,
    }


class RowStatus:
    """Status values for individual LeadImportRow."""
    PENDING = "pending"
    NEW = "new"
    UPDATE = "update"
    DUPLICATE = "duplicate"
    CONFLICT = "conflict"
    INVALID = "invalid"
    SPAM = "spam"
    NEEDS_REVIEW = "needs_review"
    COMMITTED = "committed"
    SKIPPED = "skipped"
