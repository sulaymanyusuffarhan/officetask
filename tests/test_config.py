import pytest
from pydantic import ValidationError

from app.core.config import Settings


def test_production_rejects_default_secret():
    with pytest.raises(ValidationError):
        Settings(_env_file=None, app_env="production")


def test_production_accepts_a_custom_long_secret():
    settings = Settings(
        _env_file=None,
        app_env="production",
        secret_key="a-valid-unique-production-secret-with-enough-entropy-123456",
    )

    assert settings.app_env == "production"
