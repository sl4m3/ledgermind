import re
import logging
from typing import Optional
from cryptography.fernet import Fernet

logger = logging.getLogger("agent-memory-core.compliance")

class PIIMasker:
    """Detects and masks Personally Identifiable Information (PII)."""
    
    PATTERNS = {
        "email": r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',
        "phone": r'(\+?\d{1,3}[-.\s]?\(?\d{1,3}\)?[-.\s]?\d{3}[-.\s]?\d{4})',
        "ipv4": r'\b(?:\d{1,3}\.){3}\d{1,3}\b',
        "credit_card": r'\b(?:\d{4}[-\s]?){3}\d{4}\b'
    }

    @classmethod
    def mask(cls, text: str) -> str:
        if not isinstance(text, str): return text
        masked_text = text
        for pii_type, pattern in cls.PATTERNS.items():
            masked_text = re.sub(pattern, f"[MASKED_{pii_type.upper()}]", masked_text)
        return masked_text

class MemoryEncryptor:
    """Handles encryption and decryption of memory content."""
    
    def __init__(self, key: Optional[str] = None):
        if key:
            self.fernet = Fernet(key.encode() if isinstance(key, str) else key)
        else:
            self.fernet = None

    def encrypt(self, data: str) -> str:
        if not self.fernet: return data
        return self.fernet.encrypt(data.encode()).decode()

    def decrypt(self, encrypted_data: str) -> str:
        if not self.fernet: return encrypted_data
        try:
            return self.fernet.decrypt(encrypted_data.encode()).decode()
        except Exception as e:
            logger.error(f"Decryption failed: {e}")
            return "[DECRYPTION_FAILED]"
