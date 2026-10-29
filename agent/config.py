"""
Configuration settings for the AI Research Agent.
Loaded from environment variables and .env file.
"""

from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable fallbacks."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    # API Keys
    openai_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None

    # LLM Provider selection: "mock", "openai", "gemini"
    # Auto-detects based on available API keys if left as "auto"
    llm_provider: Literal["auto", "mock", "openai", "gemini"] = "auto"

    # Model identifiers
    openai_model: str = "gpt-4o-mini"
    gemini_model: str = "gemini-2.5-flash"

    # Execution limits & timeouts
    max_search_results: int = 5
    max_pages_to_scrape: int = 3
    tool_timeout_seconds: float = 12.0
    max_plan_steps: int = 4
    max_retries: int = 3
    retry_backoff_factor: float = 1.5

    # Caching
    cache_enabled: bool = True
    cache_ttl_seconds: int = 3600

    # Safety & filtering
    relevance_threshold: float = 0.35
    max_chars_per_scraped_page: int = 8000
    strip_prompt_injections: bool = True

    # Logging
    log_level: str = "INFO"

    def resolved_provider(self) -> str:
        """Resolve provider dynamically based on available API keys."""
        if self.llm_provider != "auto":
            return self.llm_provider
        if self.gemini_api_key:
            return "gemini"
        if self.openai_api_key:
            return "openai"
        return "mock"


settings = Settings()
