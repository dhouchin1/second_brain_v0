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
    whisper_cpp_path: Path = BASE_DIR / "build/bin/whisper-cli"
    whisper_model_path: Path = BASE_DIR / "models/ggml-base.en.bin"
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
    # Transcription concurrency: allow more than one whisper job at once
    transcription_concurrency: int = 1
    # Batch processing mode: queue multiple files without immediate processing
    batch_mode_enabled: bool = False
    # Number of audio files to queue before starting batch processing
    batch_size_threshold: int = 5
    # Time to wait (seconds) before processing partial batches
    batch_timeout_seconds: int = 300  # 5 minutes
    # Split long WAVs into segments (seconds) to avoid timeouts/CPU spikes
    transcription_segment_seconds: int = 600
    # Max seconds to process a single note before marking failed:timeout
    # Increase this if you plan to upload longer audio recordings
    processing_timeout_seconds: int = 1800  # 30 minutes
    
    # Security settings
    secret_key: str = Field(
        default="your-super-secret-key-change-this-in-production",
        validation_alias=AliasChoices('secret_key', 'SECRET_KEY')
    )
    webhook_token: str = Field(
        default="your-webhook-token-change-this",
        validation_alias=AliasChoices('webhook_token', 'WEBHOOK_TOKEN')
    )
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

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

    # Email Configuration for Magic Links
    email_enabled: bool = Field(
        default=False,
        validation_alias=AliasChoices('email_enabled', 'EMAIL_ENABLED')
    )
    email_service: str = Field(
        default="resend",  # resend, sendgrid, mailgun, smtp
        validation_alias=AliasChoices('email_service', 'EMAIL_SERVICE')
    )
    email_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices('email_api_key', 'EMAIL_API_KEY', 'RESEND_API_KEY')
    )
    email_from: str = Field(
        default="noreply@localhost",
        validation_alias=AliasChoices('email_from', 'EMAIL_FROM')
    )
    email_from_name: str = Field(
        default="Second Brain",
        validation_alias=AliasChoices('email_from_name', 'EMAIL_FROM_NAME')
    )
    # SMTP Configuration (if using email_service=smtp)
    smtp_host: str | None = Field(
        default=None,
        validation_alias=AliasChoices('smtp_host', 'SMTP_HOST')
    )
    smtp_port: int = Field(
        default=587,
        validation_alias=AliasChoices('smtp_port', 'SMTP_PORT')
    )
    smtp_username: str | None = Field(
        default=None,
        validation_alias=AliasChoices('smtp_username', 'SMTP_USERNAME')
    )
    smtp_password: str | None = Field(
        default=None,
        validation_alias=AliasChoices('smtp_password', 'SMTP_PASSWORD')
    )
    smtp_use_tls: bool = Field(
        default=True,
        validation_alias=AliasChoices('smtp_use_tls', 'SMTP_USE_TLS')
    )

    # Auto-seeding Configuration
    auto_seeding_enabled: bool = Field(
        default=True,
        validation_alias=AliasChoices('auto_seeding_enabled', 'AUTO_SEEDING_ENABLED')
    )
    auto_seeding_namespace: str = Field(
        default=".starter_content",
        validation_alias=AliasChoices('auto_seeding_namespace', 'AUTO_SEEDING_NAMESPACE')
    )
    auto_seeding_embeddings: bool = Field(
        default=True,
        validation_alias=AliasChoices('auto_seeding_embeddings', 'AUTO_SEEDING_EMBEDDINGS')
    )
    auto_seeding_embed_model: str = Field(
        default="nomic-embed-text",
        validation_alias=AliasChoices('auto_seeding_embed_model', 'AUTO_SEEDING_EMBED_MODEL')
    )
    auto_seeding_skip_if_content: bool = Field(
        default=True,
        validation_alias=AliasChoices('auto_seeding_skip_if_content', 'AUTO_SEEDING_SKIP_IF_CONTENT')
    )
    auto_seeding_min_notes: int = Field(
        default=5,
        validation_alias=AliasChoices('auto_seeding_min_notes', 'AUTO_SEEDING_MIN_NOTES')
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"   # prevents crashes if other stray keys exist
    )

settings = Settings()
