import os

os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["REDIS_URL"] = "redis://127.0.0.1:1/0"
os.environ["ADMIN_API_KEY"] = "test-admin-key"
os.environ["API_KEY_HASH_SECRET"] = "test-hash-secret"
os.environ["CREDENTIAL_ENCRYPTION_KEY"] = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
os.environ["MAX_RETRIES_PER_PROVIDER"] = "0"
os.environ["RATE_LIMIT_PER_MINUTE"] = "0"
