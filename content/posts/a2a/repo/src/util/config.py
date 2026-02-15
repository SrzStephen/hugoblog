import sys

from langchain.chat_models import init_chat_model
from loguru import logger

from util.settings import mysettings


def configure_logging() -> None:
    """Remove default loguru handler and add a configured one with a consistent format."""
    logger.remove()
    logger.configure(extra={"context": ""})
    logger.add(
        sys.stderr,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level:<8} | {module}:{function}:{line} | {message} {extra[context]}",
        level="DEBUG",
    )


_model_name = mysettings.model.OPENROUTER_MODEL

api_key = (
    mysettings.model.OPENROUTER_API_KEY.get_secret_value()
    if mysettings.model.OPENROUTER_API_KEY
    else None
)
if not api_key:
    logger.warning("OPENROUTER_API_KEY is not set — LLM calls will fail")

model = None
if api_key:
    model = init_chat_model(
        model=_model_name,
        model_provider="openai",
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )
    logger.info("LLM client initialized with model={}", _model_name)
