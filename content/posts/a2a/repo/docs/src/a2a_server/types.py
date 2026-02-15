from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict

type JsonValue = (
    str | int | float | bool | None | list[JsonValue] | dict[str, JsonValue]
)


class EventType(StrEnum):
    TOOL_START = "on_tool_start"
    TOOL_END = "on_tool_end"
    CUSTOM_EVENT = "on_custom_event"
    CHAT_MODEL_STREAM = "on_chat_model_stream"


class CustomEventName(StrEnum):
    WIKIPEDIA_TOOL = "wikipedia_tool"
    WIKIPEDIA_STREAM = "wikipedia_stream"
    A2A_TOOL = "a2a_tool"
    A2A_STREAM = "a2a_stream"


class StreamEvent(BaseModel):
    model_config = ConfigDict(extra="ignore")
    event: str
    name: str
    data: dict[str, Any]


class ToolCallData(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    name: str
    input: dict[str, JsonValue] = {}


class ToolResultData(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    name: str
    output: str
