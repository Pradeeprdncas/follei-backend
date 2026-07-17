from app.crm_integrations.config import settings
from app.crm_integrations.utils.encryption import EncryptionService


class TokenService:
    def __init__(self):
        self.encryption = EncryptionService(settings.encryption_key)

    def encrypt_token(self, token: str) -> str:
        return self.encryption.encrypt(token)

    def decrypt_token(self, encrypted_token: str | None) -> str | None:
        if not encrypted_token:
            return None
        return self.encryption.decrypt(encrypted_token)
