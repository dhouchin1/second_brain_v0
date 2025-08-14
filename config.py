from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, AliasChoices




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

 # NEW: Obsidian + Raindrop
    obsidian_vault_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices('obsidian_vault_path','OBSIDIAN_VAULT_PATH')
    )
    obsidian_projects_root: str | None = Field(
        default=None,
        validation_alias=AliasChoices('obsidian_projects_root','OBSIDIAN_PROJECTS_ROOT')
    )
    obsidian_per_project: bool = Field(
        default=True,
        validation_alias=AliasChoices('obsidian_per_project','OBSIDIAN_PER_PROJECT')
    )
    raindrop_token: str | None = Field(
        default=None,
        validation_alias=AliasChoices('raindrop_token','RAINDROP_TOKEN')
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"   # prevents crashes if other stray keys exist
    )

settings = Settings()
