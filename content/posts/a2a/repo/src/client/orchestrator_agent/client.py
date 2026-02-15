import asyncio

from langchain.agents import create_agent
from rich.live import Live
from rich.markdown import Markdown
from rich.prompt import Prompt
from loguru import logger

from mcp_server.types import (
    CustomEventName,
    EventType,
    StreamEvent,
    ToolCallData,
    ToolResultData,
)
from util.config import model
from client.orchestrator_agent.agent_helpers import get_tools, get_httpx_client


async def main() -> None:
    logger.info("Orchestrator client starting")
    try:
        tools = await get_tools()
        agent = create_agent(
            model,
            tools,
            system_prompt="You are a helpful assistant that always provides citations for what you say",
        )

        user_input = Prompt.ask("[bold cyan]You[/bold cyan]")
        streamed_text = ""
        with Live(
            Markdown(streamed_text),
            refresh_per_second=8,
            vertical_overflow="visible",
            screen=False,
        ) as live:
            async for raw_event in agent.astream_events(
                {"messages": [("user", user_input)]},
                version="v2",
            ):
                event = StreamEvent.model_validate(raw_event)
                if event.event == EventType.TOOL_END:
                    streamed_text += f"\n\n> {event.name} finished\n\n"
                elif event.event == EventType.CUSTOM_EVENT:
                    if event.name == CustomEventName.A2A_TOOL:
                        data = event.data
                        if data["type"] == "tool_call":
                            tc = ToolCallData(**data)
                            streamed_text += (
                                f"\n\n`[tool_call]` {tc.name}({tc.input})\n\n"
                            )
                        elif data["type"] == "tool_result":
                            tr = ToolResultData(**data)
                            streamed_text += f"\n\n`[tool_result]` {tr.name}: {tr.output[:200]}...\n\n"
                    elif event.name == CustomEventName.A2A_STREAM:
                        streamed_text += event.data["text"]
                elif event.event == EventType.CHAT_MODEL_STREAM:
                    chunk = event.data.get("chunk", {})
                    content = (
                        chunk.content
                        if hasattr(chunk, "content")
                        else chunk.get("content")
                    )
                    if content and isinstance(content, str):
                        streamed_text += content
                live.update(Markdown(streamed_text), refresh=True)
    finally:
        logger.info("Orchestrator client shutting down")
        client = get_httpx_client()
        await client.aclose()


if __name__ == "__main__":
    asyncio.run(main())
