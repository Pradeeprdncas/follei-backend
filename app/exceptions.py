"""Custom exceptions."""

class FolleiException(Exception):
    """Base exception."""
    pass


class DocumentNotFoundException(FolleiException):
    """Document not found."""
    pass


class IndexingException(FolleiException):
    """Indexing failed."""
    pass


class RetrievalException(FolleiException):
    """Retrieval failed."""
    pass
