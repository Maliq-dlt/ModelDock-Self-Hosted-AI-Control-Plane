from app.core.security import create_api_key, decrypt_credentials, encrypt_credentials, hash_api_key


def test_api_keys_are_hashed_and_prefixed() -> None:
    raw_key, prefix, key_hash = create_api_key("test")
    assert raw_key.startswith("md_test_")
    assert prefix == raw_key[:16]
    assert key_hash == hash_api_key(raw_key)
    assert raw_key not in key_hash


def test_provider_credentials_round_trip_encrypted() -> None:
    encrypted = encrypt_credentials({"api_key": "secret-value"})
    assert "secret-value" not in encrypted
    assert decrypt_credentials(encrypted) == {"api_key": "secret-value"}
