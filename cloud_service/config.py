"""Fail-closed deployment settings; public passwords have no complexity rule."""
from dataclasses import dataclass
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    database_url: str
    secret: str
    origins: tuple[str, ...]
    environment: str = "production"
    doctor_username: str = "doctor"

    def __post_init__(self):
        if self.environment not in {"production", "development", "test"}:
            raise ValueError("Unknown CLOUD_ENV")
        if len(self.secret) < 32:
            raise ValueError("CLOUD_SECRET must contain at least 32 characters")
        if not self.origins:
            raise ValueError("CLOUD_ORIGINS is required")
        for origin in self.origins:
            parsed = urlsplit(origin)
            if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path:
                raise ValueError("CLOUD_ORIGINS must contain exact origins without paths")
            if parsed.scheme not in {"https", "http"} or self.production and parsed.scheme != "https":
                raise ValueError("Production origins must use HTTPS")
        if self.production and not self.database_url.startswith("postgresql+psycopg://"):
            raise ValueError("Production requires PostgreSQL")

    @property
    def production(self):
        return self.environment == "production"

    @property
    def cookie_name(self):
        return "__Host-ankang-session" if self.production else "ankang-session"

    @classmethod
    def from_env(cls):
        return cls(
            database_url=os.environ["CLOUD_DATABASE_URL"],
            secret=os.environ["CLOUD_SECRET"],
            origins=tuple(x.strip() for x in os.environ["CLOUD_ORIGINS"].split(",") if x.strip()),
            environment=os.environ.get("CLOUD_ENV", "production"),
            doctor_username=os.environ.get("CLOUD_DOCTOR_USERNAME", "doctor"),
        )
