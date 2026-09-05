"""Application configuration.

All configuration is environment-driven (12-factor). Secrets are never
hard-coded; they are read from the environment or a secret manager. Defaults
are safe for local development and deterministic tests.
"""

from __future__ import annotations

import os
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class DatabaseSettings(BaseSettings):
    """PostgreSQL / PostGIS / TimescaleDB connection settings."""

    model_config = SettingsConfigDict(env_prefix="MDE_DB_", extra="ignore")

    host: str = "localhost"
    port: int = 5432
    name: str = "marine"
    user: str = "marine"
    password: str = Field(default="marine", repr=False)
    # When set, this DSN overrides the discrete fields above. Useful for tests
    # (e.g. a SQLite in-memory URL) and managed database services.
    url_override: str | None = None

    @property
    def url(self) -> str:
        if self.url_override:
            return self.url_override
        # Precedence: url_override (explicit DSN) > DATABASE_URL env var >
        # discrete MDE_DB_* fields. This lets compose/managed services inject a
        # single DSN while tests can pin an in-memory SQLite URL.
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            return db_url
        return (
            f"postgresql+psycopg://{self.user}:{self.password}"
            f"@{self.host}:{self.port}/{self.name}"
        )


class ObjectStoreSettings(BaseSettings):
    """MinIO / S3 immutable raw object storage settings."""

    model_config = SettingsConfigDict(env_prefix="MDE_S3_", extra="ignore")

    endpoint_url: str | None = "http://localhost:9000"
    region: str = "us-east-1"
    access_key: str = Field(default="minioadmin", repr=False)
    secret_key: str = Field(default="minioadmin", repr=False)
    raw_bucket: str = "marine-raw"
    processed_bucket: str = "marine-processed"
    artifact_bucket: str = "marine-artifacts"
    # When true, storage writes are recorded to an in-process store instead of
    # calling MinIO/S3. Tests always run enabled.
    in_memory: bool = False


class MessagingSettings(BaseSettings):
    """NATS JetStream messaging settings."""

    model_config = SettingsConfigDict(env_prefix="MDE_NATS_", extra="ignore")

    servers: str = "nats://localhost:4222"
    stream_prefix: str = "MARINE"
    max_deliver: int = 5
    ack_wait_seconds: int = 30
    # Base backoff (seconds) for redelivery; grows exponentially with jitter.
    backoff_base_seconds: float = 2.0
    backoff_max_seconds: float = 300.0


class SourceCredentialsSettings(BaseSettings):
    """Credentials for authenticated upstream connectors.

    These are intentionally blank by default. Missing credentials are surfaced
    as explicit auth-blocked source states; workers never substitute fixtures.
    """

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")

    mosdac_username: str = Field(default="", repr=False, alias="MOSDAC_USERNAME")
    mosdac_password: str = Field(default="", repr=False, alias="MOSDAC_PASSWORD")
    imd_api_token: str = Field(default="", repr=False, alias="IMD_API_TOKEN")

    @property
    def mosdac_ready(self) -> bool:
        return bool(self.mosdac_username and self.mosdac_password)

    @property
    def imd_token_ready(self) -> bool:
        return bool(self.imd_api_token)


class ServiceSettings(BaseSettings):
    """Top-level service settings."""

    model_config = SettingsConfigDict(env_prefix="MDE_", extra="ignore")

    environment: str = "development"
    log_level: str = "INFO"
    log_json: bool = True
    # Live source connectors are disabled by default. Workers record a disabled
    # source state and never ingest fixtures implicitly; fixture adapters are
    # available only to tests or explicit callers.
    enable_live_sources: bool = False
    # Datasets are considered stale past this multiple of their expected
    # update interval unless a per-dataset override is configured.
    default_stale_multiplier: float = 3.0
    # Redis is used only as a lazy-population / single-flight cache in front of
    # scraped upstream documents. It is strictly optional: an unset URL or an
    # unreachable server degrades to uncached direct fetches, never to failure.
    redis_url: str = ""
    bulletin_cache_ttl_s: int = 900
    # Bounded radius for resolving a requested coordinate to a wet WaveWatch III
    # grid node. An unbounded search could answer a coastal query with an
    # open-ocean node far offshore and still look plausible.
    ww3_search_radius_km: float = 30.0
    # Sent when scraping public government bulletin pages. Operators should set
    # an identifying contact string; generic agents are commonly rejected.
    imd_bulletin_user_agent: str = "MarineDataEngine/0.1 (+marine-data-engine)"


class Settings(BaseSettings):
    """Aggregate settings container."""

    model_config = SettingsConfigDict(extra="ignore")

    service: ServiceSettings = Field(default_factory=ServiceSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    object_store: ObjectStoreSettings = Field(default_factory=ObjectStoreSettings)
    messaging: MessagingSettings = Field(default_factory=MessagingSettings)
    credentials: SourceCredentialsSettings = Field(
        default_factory=SourceCredentialsSettings
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return a cached Settings instance."""
    return Settings()
