from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import HttpUrl, SecretStr
from typing import Optional
from uuid import UUID

import httpx
from loguru import logger

from pathlib import Path

base_path = Path(__file__).parent.parent.parent / ".env"

logger.info(f"Looking for settings in {base_path}, found {base_path.exists()}")


class DotEnvBase(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", env_file=base_path)


class EntraSettings(DotEnvBase):
    AZURE_TENANT_ID: Optional[UUID] = None
    AZURE_CLIENT_ID: Optional[UUID] = None
    AZURE_CLIENT_SECRET: Optional[SecretStr] = None
    AZURE_REDIRECT_URI: Optional[HttpUrl] = None
    AZURE_AGENT_CALLER_ROLE: str = "agent.caller"

    def entra_is_enabled(self) -> bool:
        return all(
            [
                self.AZURE_TENANT_ID,
                self.AZURE_CLIENT_ID,
                self.AZURE_CLIENT_SECRET,
            ]
        )

    def validate_entra_credentials(self) -> bool:
        """Request a token using client credentials to verify the client ID and secret are valid."""
        if not self.entra_is_enabled():
            logger.warning("Entra is not enabled — skipping credential validation")
            return False

        token_url = f"https://login.microsoftonline.com/{self.AZURE_TENANT_ID}/oauth2/v2.0/token"
        try:
            resp = httpx.post(
                token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": str(self.AZURE_CLIENT_ID),
                    "client_secret": self.AZURE_CLIENT_SECRET.get_secret_value(),
                    "scope": f"{self.AZURE_CLIENT_ID}/.default",
                },
                timeout=10,
            )
            if resp.status_code == 200:
                logger.info("Entra credential validation succeeded")
                return True
            else:
                error = resp.json().get("error_description", resp.text)
                logger.error("Entra credential validation failed: {}", error)
                return False
        except httpx.HTTPError as e:
            logger.error("Entra credential validation request failed: {}", e)
            return False


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
__all__ = ["mysettings"]
