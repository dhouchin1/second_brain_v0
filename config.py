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
    uploads_dir: Path = BASE_DIR / "uploads"
    # Maximum size (in bytes) for any uploaded file (audio/images/pdfs)
    # Can be overridden via env var MAX_FILE_SIZE
    max_file_size: int = 200 * 1024 * 1024  # 200MB default
    whisper_cpp_path: Path = BASE_DIR / "whisper.cpp/build/bin/whisper-cli"
    whisper_model_path: Path = BASE_DIR / "whisper.cpp/models/ggml-base.en.bin"
    # Transcription backend: 'whisper' (whisper.cpp) or 'vosk' (lightweight, CPU-only)
    transcriber: str = "whisper"
    # Path to Vosk ASR model directory when using transcriber='vosk'
    vosk_model_path: Path | None = None
    ollama_api_url: str = "http://localhost:11434/api/generate"
    ollama_model: str = "llama3.2"
    # Optional Ollama performance/resource knobs
    ollama_num_ctx: int | None = None
    ollama_num_predict: int | None = None
    ollama_temperature: float | None = None
    ollama_top_p: float | None = None
    ollama_num_gpu: int | None = None
    # AI processing controls (to reduce local CPU/RAM usage)
    ai_processing_enabled: bool = True
    ai_chunk_size_chars: int = 1500
    ai_throttle_delay_seconds: int = 2
    # Processing concurrency for background audio transcription/LLM jobs
    processing_concurrency: int = 2
    # Transcription concurrency (serialize transcription one-at-a-time)
    transcription_concurrency: int = 1
    # Max seconds to process a single note before marking failed:timeout
    # Increase this if you plan to upload longer audio recordings
    processing_timeout_seconds: int = 1800  # 30 minutes

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

    # Advanced Search Configuration
    search_rerank_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices('search_rerank_enabled', 'SEARCH_RERANK_ENABLED')
    )
    search_rerank_top_k: int = Field(
        default=20,
        validation_alias=AliasChoices('search_rerank_top_k', 'SEARCH_RERANK_TOP_K')
    )
    search_rerank_final_k: int = Field(
        default=8,
        validation_alias=AliasChoices('search_rerank_final_k', 'SEARCH_RERANK_FINAL_K')
    )
    search_rerank_weight: float = Field(
        default=0.7,
        validation_alias=AliasChoices('search_rerank_weight', 'SEARCH_RERANK_WEIGHT')
    )
    search_original_weight: float = Field(
        default=0.3,
        validation_alias=AliasChoices('search_original_weight', 'SEARCH_ORIGINAL_WEIGHT')
    )
    search_cross_encoder_model: str = Field(
        default="cross-encoder/ms-marco-MiniLM-L-6-v2",
        validation_alias=AliasChoices('search_cross_encoder_model', 'SEARCH_CROSS_ENCODER_MODEL')
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"   # prevents crashes if other stray keys exist
    )

settings = Settings()
