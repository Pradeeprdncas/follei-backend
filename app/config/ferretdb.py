"""Lazy authenticated FerretDB client."""
from pymongo import MongoClient
from app.config.settings import get_settings

_settings = get_settings()
_client = None

def get_context_database():
    global _client
    if _client is None:
        url = _settings.FERRETDB_URL
        if _settings.FERRETDB_USER and _settings.FERRETDB_PASSWORD and "@" not in url:
            url = url.replace("mongodb://", f"mongodb://{_settings.FERRETDB_USER}:{_settings.FERRETDB_PASSWORD}@", 1)
        _client = MongoClient(url, serverSelectionTimeoutMS=1500, connectTimeoutMS=1500)
    return _client[_settings.FERRETDB_DATABASE]
