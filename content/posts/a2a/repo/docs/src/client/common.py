import uuid

from a2a.types import (
    DataPart,
    Message,
    Part,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatusUpdateEvent,
    TextPart,
)
from langchain_core.callbacks import adispatch_custom_event
from langchain_core.tools import BaseTool, tool
from loguru import logger

from mcp_server.types import CustomEventName
from util.settings import mysettings

BASE_URL = mysettings.server.A2A_BASE_URL


def make_message(text: str) -> Message:
    return Message(
        role="user",
        message_id=str(uuid.uuid4()),
        parts=[Part(root=TextPart(text=text))],
    )


def first_part(event: TaskStatusUpdateEvent) -> TextPart | DataPart | None:
    if event.status.message and event.status.message.parts:
        return event.status.message.parts[0].root
    return None


async def call_a2a_agent(client, query: str) -> str:
    """Shared A2A call logic for any agent.

    Args:
        client: An A2A client (from ClientFactory.connect).
        query: The search query.

    Returns:
        The agent's text response, or an error string.
    """
    parts: list[str] = []
    async for result in client.send_message(make_message(query)):
        if not isinstance(result, tuple):
            continue
        _, event = result

        if isinstance(event, TaskArtifactUpdateEvent):
            for part in event.artifact.parts:
                if isinstance(part.root, TextPart):
                    parts.append(part.root.text)
            continue

        if not isinstance(event, TaskStatusUpdateEvent):
            continue

        if event.status.state == TaskState.failed:
            logger.warning("A2A agent returned failed state")
            fp = first_part(event)
            return fp.text if isinstance(fp, TextPart) else "Agent call failed."

        fp = first_part(event)
        if isinstance(fp, DataPart):
            await adispatch_custom_event(CustomEventName.A2A_TOOL, fp.data)
        elif isinstance(fp, TextPart):
            await adispatch_custom_event(CustomEventName.A2A_STREAM, {"text": fp.text})

    return "\n".join(parts) if parts else "No results found."


def make_a2a_tool(name: str, description: str, client) -> BaseTool:
    """Create a LangChain tool that calls an A2A agent.

    Args:
        name: Tool name (derived from agent card name).
        description: Tool description (derived from agent card description).
        client: An A2A client (from ClientFactory.connect).

    Returns:
        A @tool-decorated async function.
    """

    async def _a2a_tool(query: str) -> str:
        """Placeholder docstring."""
        logger.info("{}() called — query_length={}", name, len(query))
        try:
            return await call_a2a_agent(client, query)
        except Exception:
            logger.exception("A2A call to {} failed", name)
            return f"Error: failed to reach the {name} agent."

    _a2a_tool.__doc__ = description
    _a2a_tool.__name__ = name
    return tool(_a2a_tool)
