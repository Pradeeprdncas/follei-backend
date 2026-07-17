"""Custom exceptions for the Lead Import domain."""


class LeadImportError(Exception):
    """Base exception for lead import operations."""
    def __init__(self, message: str, details: dict | None = None):
        self.message = message
        self.details = details or {}
        super().__init__(self.message)


class FileTypeNotSupported(LeadImportError):
    """Raised when the uploaded file type is not supported."""
    def __init__(self, filename: str, detected_type: str | None = None):
        super().__init__(
            message=f"File type not supported: {filename}",
            details={"filename": filename, "detected_type": detected_type},
        )


class ParsingError(LeadImportError):
    """Raised when file parsing fails."""
    def __init__(self, filename: str, reason: str):
        super().__init__(
            message=f"Failed to parse {filename}: {reason}",
            details={"filename": filename, "reason": reason},
        )


class ValidationError(LeadImportError):
    """Raised when validation of extracted data fails."""
    def __init__(self, row_index: int, field: str, reason: str):
        super().__init__(
            message=f"Validation failed for row {row_index}, field '{field}': {reason}",
            details={"row_index": row_index, "field": field, "reason": reason},
        )


class JobNotFoundError(LeadImportError):
    """Raised when a LeadImportJob is not found."""
    def __init__(self, job_id: str):
        super().__init__(
            message=f"Lead import job not found: {job_id}",
            details={"job_id": job_id},
        )


class JobNotReadyError(LeadImportError):
    """Raised when an operation is attempted on a job in the wrong state."""
    def __init__(self, job_id: str, current_status: str, required_status: str):
        super().__init__(
            message=f"Job {job_id} is in status '{current_status}', expected '{required_status}'",
            details={"job_id": job_id, "current_status": current_status, "required_status": required_status},
        )
