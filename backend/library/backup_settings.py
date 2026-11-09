"""Environment-driven operational backup policy."""

from datetime import time
import re
from zoneinfo import ZoneInfo

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BackupSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='BACKUP_', extra='ignore')

    enabled: bool = False
    time: str = '04:00'
    timezone: str = 'Asia/Seoul'
    minio_bucket: str = 'kaifind-db-backups'
    minio_prefix: str = 'postgres/'
    retention_days: int = 7
    poll_seconds: int = 30
    timeout_seconds: int = 1800
    max_attempts: int = 3
    retry_seconds: str = '60,300'
    catch_up_enabled: bool = True

    @field_validator('time')
    @classmethod
    def valid_time(cls, value):
        if not re.fullmatch(r'\d{2}:\d{2}', value):
            raise ValueError('Expected HH:MM')
        time.fromisoformat(value)
        return value

    @field_validator('timezone')
    @classmethod
    def valid_timezone(cls, value):
        ZoneInfo(value)
        return value

    @field_validator('retention_days', 'poll_seconds', 'timeout_seconds', 'max_attempts')
    @classmethod
    def positive(cls, value):
        if value < 1:
            raise ValueError('Must be positive')
        return value

    @field_validator('minio_bucket')
    @classmethod
    def valid_bucket(cls, value):
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]', value):
            raise ValueError('Invalid backup bucket')
        return value

    @field_validator('minio_prefix')
    @classmethod
    def valid_prefix(cls, value):
        if not value or value.startswith('/') or '..' in value.split('/'):
            raise ValueError('Expected nonempty relative prefix')
        return value.rstrip('/') + '/'

    @model_validator(mode='after')
    def valid_retries(self):
        try:
            delays = [int(part) for part in self.retry_seconds.split(',')]
        except ValueError:
            raise ValueError('Expected comma-separated retry seconds') from None
        if any(delay < 1 for delay in delays) or len(delays) < self.max_attempts - 1:
            raise ValueError('Provide a positive delay for each retry')
        return self

    @property
    def retry_delays(self):
        return tuple(int(part) for part in self.retry_seconds.split(','))
