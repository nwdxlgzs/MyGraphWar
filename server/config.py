from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]

class Settings(BaseSettings):
    host: str = "127.0.0.1"
    port: int = 8000
    database_url: str = f"sqlite:///{(ROOT / 'mygraphwar.db').as_posix()}"
    session_days: int = 30
    max_rooms: int = 50
    model_config = SettingsConfigDict(env_prefix="MGW_", env_file=".env")

settings = Settings()

