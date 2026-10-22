from functools import lru_cache
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="PARKWISE_", env_file=".env", extra="ignore")

    env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    allowed_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    database_url: str = "sqlite:///./data/parkwise.db"
    data_dir: str = "./data"
    max_upload_mb: int = 250
    max_video_seconds: int = 1800
    model: str = "yolo26s.pt"
    confidence: float = 0.25
    image_size: int = 1280
    frame_stride: int = 3
    device: str = "auto"
    multiscale: bool = True
    auto_download_public_sources: bool = True
    # Security / limits (0 disables a check; see docs/SECURITY.md)
    auth_required: bool = False
    rate_limit_per_minute: int = 240
    # Live view streaming
    stream_width: int = 960
    stream_quality: int = 72
    stream_max_seconds: int = 0  # 0 = run until stopped; guard against runaway sources

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def data_path(self) -> Path:
        path = Path(self.data_dir).expanduser().resolve()
        for folder in ("uploads", "processed", "previews", "streams"):
            (path / folder).mkdir(parents=True, exist_ok=True)
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
