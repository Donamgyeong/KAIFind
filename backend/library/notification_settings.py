"""Validated deployment settings for notification email delivery."""

import math
import os
import re
from dataclasses import dataclass
from datetime import time
from urllib.parse import urlsplit


@dataclass(frozen=True)
class NotificationSettings:
    enabled: bool = False
    daily_limit: int = 20
    digest_time: time = time(20)
    poll_seconds: float = 5
    lease_seconds: float = 120
    timeout_seconds: float = 30
    retry_seconds: tuple[int, ...] = (60, 300, 1800)
    retry_jitter_ratio: float = 0.2
    max_attempts: int = 10
    provider: str = 'mock'
    app_base_url: str = ''

    def __post_init__(self):
        if (type(self.enabled) is not bool or type(self.daily_limit) is not int
                or not 1 <= self.daily_limit <= 2147483647):
            raise ValueError('Invalid notification email enabled/daily limit')
        if not isinstance(self.digest_time, time) or self.digest_time.tzinfo is not None:
            raise ValueError('Invalid notification digest time')
        numbers = (self.poll_seconds, self.lease_seconds, self.timeout_seconds)
        if any(not math.isfinite(n) or n <= 0 for n in numbers):
            raise ValueError('Notification email durations must be finite and positive')
        if self.timeout_seconds >= self.lease_seconds:
            raise ValueError('Notification timeout must be shorter than lease')
        if (not self.retry_seconds or any(type(n) is not int or n <= 0 for n in self.retry_seconds)
                or tuple(sorted(self.retry_seconds)) != self.retry_seconds):
            raise ValueError('Notification retry intervals must be positive and sorted')
        if (not 0 <= self.retry_jitter_ratio <= 1 or type(self.max_attempts) is not int
                or self.max_attempts < 1):
            raise ValueError('Invalid notification retry policy')
        if self.provider != 'mock':
            raise ValueError('Only the mock notification email provider is implemented')
        if self.enabled:
            url = urlsplit(self.app_base_url)
            if (url.scheme != 'https' or not url.netloc or url.username or url.password
                    or url.path not in ('', '/') or url.query or url.fragment):
                raise ValueError('NOTIFICATION_EMAIL_APP_BASE_URL must be an HTTPS origin')

    @classmethod
    def from_environment(cls):
        def env(key, default):
            return os.getenv('NOTIFICATION_EMAIL_' + key, default)

        enabled = env('ENABLED', 'false')
        if enabled not in ('true', 'false'):
            raise ValueError('NOTIFICATION_EMAIL_ENABLED must be true or false')
        raw_time = env('DIGEST_TIME', '20:00')
        if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', raw_time):
            raise ValueError('NOTIFICATION_EMAIL_DIGEST_TIME must be HH:MM')
        return cls(
            enabled=enabled == 'true', daily_limit=int(env('DAILY_LIMIT', '20')),
            digest_time=time.fromisoformat(raw_time), poll_seconds=float(env('POLL_SECONDS', '5')),
            lease_seconds=float(env('LEASE_SECONDS', '120')),
            timeout_seconds=float(env('TIMEOUT_SECONDS', '30')),
            retry_seconds=tuple(int(n) for n in env('RETRY_SECONDS', '60,300,1800').split(',')),
            retry_jitter_ratio=float(env('RETRY_JITTER_RATIO', '0.2')),
            max_attempts=int(env('MAX_ATTEMPTS', '10')), provider=env('PROVIDER', 'mock'),
            app_base_url=env('APP_BASE_URL', '').rstrip('/'),
        )
