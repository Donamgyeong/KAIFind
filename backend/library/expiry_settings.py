"""Operational expiry policy; the domain's 30-day lifetime stays unchanged."""

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class ExpirySettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='EXPIRY_', extra='ignore')

    batch_size: int = Field(default=100, ge=1, le=10000)
    max_attempts: int = Field(default=3, ge=1)
    retry_seconds: str = '60,300'
    lock_timeout_seconds: int = Field(default=10, ge=1, le=300)

    @model_validator(mode='after')
    def validate_retries(self):
        delays = self.retry_delays
        if any(value < 1 for value in delays) or len(delays) < self.max_attempts - 1:
            raise ValueError('Provide positive retry delays for all retries')
        return self

    @property
    def retry_delays(self):
        return tuple(int(value) for value in self.retry_seconds.split(','))
