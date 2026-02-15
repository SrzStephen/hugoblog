from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import HttpUrl, SecretStr
from typing import Optional
from uuid import UUID
from loguru import logger

from pathlib import Path

base_path = Path(__file__).parent.parent.parent / ".env"


class DotEnvBase(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=base_path)


class EntraSettings(DotEnvBase):
    AZURE_TENANT_ID: Optional[UUID] = None
    AZURE_CLIENT_ID: Optional[UUID] = None
    AZURE_CLIENT_SECRET: Optional[SecretStr] = None
    AZURE_REDIRECT_URI: Optional[HttpUrl] = None
    AZURE_AGENT_CALLER_ROLE: str = "agent.caller"


class ModelSettings(DotEnvBase):
    OPENROUTER_API_KEY: SecretStr
    OPENROUTER_MODEL: str = "google/gemini-2.5-flash"


class ServerSettings(DotEnvBase):
    A2A_BASE_URL: str = "http://localhost:9999"
    LOG_LEVEL: str = "WARNING"


class AllSettings(DotEnvBase):
    entra: EntraSettings = EntraSettings()
    model: ModelSettings = ModelSettings()
    server: ServerSettings = ServerSettings()


mysettings = AllSettings()
logger.remove()
logger.add(sink=__import__("sys").stderr, level=mysettings.server.LOG_LEVEL)
logger.info(f"Looking for settings in {base_path}, found {base_path.exists()}")
__all__ = ["mysettings"]
