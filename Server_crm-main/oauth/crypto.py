import logging
from cryptography.fernet import Fernet
from config import settings

logger = logging.getLogger("crm_gateway.oauth.crypto")

# Maintain a single in-memory fallback key for local dev if config lacks ENCRYPTION_KEY
_fallback_key = None

def _get_encryption_key() -> str:
    global _fallback_key
    key = settings.ENCRYPTION_KEY
    if not key:
        if not _fallback_key:
            _fallback_key = Fernet.generate_key().decode()
            logger.warning(
                "ENCRYPTION_KEY is not set in environment or config settings. "
                "Generating a temporary in-memory key: %s. "
                "ALL stored credentials will become undecryptable if the server restarts!",
                _fallback_key
            )
        return _fallback_key
    return key


class CryptoUtil:
    """
    Utility for secure symmetric encryption and decryption of secrets using Fernet.
    """
    def __init__(self):
        key = _get_encryption_key()
        try:
            self.fernet = Fernet(key.strip().encode())
        except Exception as e:
            logger.error(f"Failed to initialize Fernet with configured key: {str(e)}")
            # Fallback to in-memory key to prevent system crash
            global _fallback_key
            if not _fallback_key:
                _fallback_key = Fernet.generate_key().decode()
            self.fernet = Fernet(_fallback_key.encode())

    def encrypt(self, plain_text: str | None) -> str | None:
        """Encrypt plain text to secure cipher text."""
        if plain_text is None:
            return None
        return self.fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

    def decrypt(self, cipher_text: str | None) -> str | None:
        """Decrypt cipher text back to plain text."""
        if cipher_text is None:
            return None
        try:
            return self.fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
        except Exception as e:
            logger.error(f"Token decryption failed: {str(e)}")
            raise ValueError("Token decryption failed. The encryption key is incorrect or has changed.") from e
