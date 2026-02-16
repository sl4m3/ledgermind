import pytest
from agent_memory_core.core.compliance import PIIMasker, MemoryEncryptor
from cryptography.fernet import Fernet

def test_pii_masker():
    text = "Contact me at test@example.com or call +1 (555) 000-1234. My IP is 192.168.1.1."
    masked = PIIMasker.mask(text)
    
    assert "[MASKED_EMAIL]" in masked
    assert "[MASKED_PHONE]" in masked
    assert "[MASKED_IPV4]" in masked
    assert "test@example.com" not in masked
    assert "192.168.1.1" not in masked

def test_memory_encryptor():
    key = Fernet.generate_key().decode()
    encryptor = MemoryEncryptor(key)
    
    secret_data = "Strategic plan for 2026"
    encrypted = encryptor.encrypt(secret_data)
    assert encrypted != secret_data
    
    decrypted = encryptor.decrypt(encrypted)
    assert decrypted == secret_data

def test_encryptor_no_key():
    encryptor = MemoryEncryptor(None)
    data = "Public info"
    assert encryptor.encrypt(data) == data
    assert encryptor.decrypt(data) == data

def test_encryptor_invalid_data():
    key = Fernet.generate_key().decode()
    encryptor = MemoryEncryptor(key)
    assert encryptor.decrypt("not encrypted at all") == "[DECRYPTION_FAILED]"
