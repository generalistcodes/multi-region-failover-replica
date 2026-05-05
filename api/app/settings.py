from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=None, extra="ignore")

    region_a_dsn: str
    region_b_dsn: str
    region_c_dsn: str | None = None
    region_d_dsn: str | None = None
    region_e_dsn: str | None = None

    # Comma-separated list of enabled regions (UI toggle + load reduction)
    enabled_regions: str = "region-a,region-b"

    active_region_file: str = "/state/active_region.txt"
    default_active_region: str = "region-a"

    log_level: str = "info"
    # Write safety: when writing to region-a, ensure standby isn't far behind.
    # This uses WAL LSN lag bytes (not "seconds since last replay").
    max_replica_wal_lag_bytes: int = 1024 * 1024  # 1 MiB

    # Decision layer tuning
    decision_failure_stable_seconds: float = 6.0
    # Primary->standby WAL lag threshold for allowing promotion.
    decision_wal_lag_bytes_threshold: int = 1024 * 1024  # 1 MiB


settings = Settings()

