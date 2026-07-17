import base64
import hashlib
from cryptography.fernet import Fernet


class EncryptionService:
    def __init__(self, key: str):
        if not key:
            raise ValueError("ENCRYPTION_KEY is required.")
        digest = hashlib.sha256(key.encode("utf-8")).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(digest))

    def encrypt(self, value: str) -> str:
        return self.fernet.encrypt(value.encode("utf-8")).decode("utf-8")

    def decrypt(self, value: str) -> str:
        return self.fernet.decrypt(value.encode("utf-8")).decode("utf-8")
