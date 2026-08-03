"""DevFlow configuration system.

Loads from environment variables and .env files.
DeepSeek API is used via the Anthropic-compatible endpoint.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class LLMConfig:
    """LLM API configuration."""

    api_key: str = ""
    base_url: str = "https://api.deepseek.com/anthropic"
    default_model: str = "deepseek-v4-pro"
    fast_model: str = "deepseek-v4-flash"
    max_tokens: int = 4096
    temperature: float = 0.1
    max_retries: int = 3
    timeout_seconds: float = 60.0


@dataclass
class StorageConfig:
    """Storage backend configuration."""

    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = ""
    minio_secret_key: str = ""
    minio_bucket: str = "devflow"
    qdrant_url: str = "http://localhost:6333"
    loki_url: str = "http://localhost:3100"


@dataclass
class PipelineConfig:
    """Pipeline behavior configuration."""

    default_complexity: str = "L"
    auto_approve_enabled: bool = False
    trust_threshold_auto: float = 0.85
    human_timeout_hours: int = 4
    max_retry_attempts: int = 3


@dataclass
class DevFlowConfig:
    """Master configuration for DevFlow."""

    llm: LLMConfig = field(default_factory=LLMConfig)
    storage: StorageConfig = field(default_factory=StorageConfig)
    pipeline: PipelineConfig = field(default_factory=PipelineConfig)
    project_name: str = "devflow"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "DevFlowConfig":
        """Load configuration from environment variables."""
        llm = LLMConfig(
            api_key=os.getenv("DEEPSEEK_API_KEY", ""),
            base_url=os.getenv("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"),
            default_model=os.getenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "deepseek-v4-pro"),
            fast_model=os.getenv("ANTHROPIC_DEFAULT_HAIKU_MODEL", "deepseek-v4-flash"),
            max_tokens=int(os.getenv("DEVFLOW_MAX_TOKENS", "4096")),
            temperature=float(os.getenv("DEVFLOW_TEMPERATURE", "0.1")),
            max_retries=int(os.getenv("DEVFLOW_MAX_RETRIES", "3")),
            timeout_seconds=float(os.getenv("DEVFLOW_TIMEOUT", "60")),
        )

        storage = StorageConfig(
            minio_endpoint=os.getenv("MINIO_ENDPOINT", "localhost:9000"),
            minio_access_key=os.getenv("MINIO_ACCESS_KEY", ""),
            minio_secret_key=os.getenv("MINIO_SECRET_KEY", ""),
            minio_bucket=os.getenv("MINIO_BUCKET", "devflow"),
            qdrant_url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            loki_url=os.getenv("LOKI_URL", "http://localhost:3100"),
        )

        pipeline = PipelineConfig(
            default_complexity=os.getenv("DEVFLOW_DEFAULT_COMPLEXITY", "L"),
            auto_approve_enabled=os.getenv("DEVFLOW_AUTO_APPROVE", "false").lower() == "true",
            trust_threshold_auto=float(os.getenv("DEVFLOW_TRUST_THRESHOLD", "0.85")),
            human_timeout_hours=int(os.getenv("DEVFLOW_HUMAN_TIMEOUT", "4")),
            max_retry_attempts=int(os.getenv("DEVFLOW_MAX_RETRY_ATTEMPTS", "3")),
        )

        return cls(
            llm=llm,
            storage=storage,
            pipeline=pipeline,
            project_name=os.getenv("DEVFLOW_PROJECT", "devflow"),
            log_level=os.getenv("DEVFLOW_LOG_LEVEL", "INFO"),
        )


# Global config instance
_config: Optional[DevFlowConfig] = None


def get_config() -> DevFlowConfig:
    """Get the global configuration, loading from env if needed."""
    global _config
    if _config is None:
        _config = DevFlowConfig.from_env()
    return _config


def reload_config():
    """Force reload configuration from environment."""
    global _config
    _config = DevFlowConfig.from_env()
    return _config
