from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).parent.resolve()

class Settings(BaseSettings):
    """Application configuration loaded from environment variables."""

    base_dir: Path = BASE_DIR
    db_path: Path = BASE_DIR / "notes.db"
    vault_path: Path = BASE_DIR
    audio_dir: Path = BASE_DIR / "audio"
    whisper_cpp_path: Path = BASE_DIR / "whisper.cpp/build/bin/whisper-cli"
    whisper_model_path: Path = BASE_DIR / "whisper.cpp/models/ggml-base.en.bin"
    ollama_api_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "llama3.2"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


settings = Settings()
