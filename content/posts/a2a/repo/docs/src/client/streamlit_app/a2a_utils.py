from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import AgentCard
import streamlit as st
from langchain.agents import create_agent
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from loguru import logger
from datetime import datetime
from client.common import (
    BASE_URL,
    make_a2a_tool,
    make_message as _make_message,
    first_part as _first_part,
)
from a2a_server.types import (
    CustomEventName,
    EventType,
    StreamEvent,
    ToolCallData,
    ToolResultData,
)
from util.config import model
from client.streamlit_app.auth import get_id_token


@asynccontextmanager
async def http_client() -> AsyncGenerator[
    tuple[httpx.AsyncClient, dict[str, Any]], None
]:
    """Async context manager that creates an httpx client, discovers A2A agents, and yields (client, agents)."""
    headers = {}
    id_token = get_id_token()
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(300, connect=30),
        headers=headers,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    try:
        resp = await client.get(f"{BASE_URL}/agents")
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"Expected list of agent cards, got {type(data).__name__}")
        cards = [AgentCard(**card) for card in data]
        clients = {}
        for card in cards:
            a2a_client = await ClientFactory.connect(
                card,
                client_config=ClientConfig(httpx_client=client),
            )
            clients[card.name] = a2a_client
        logger.info("Initialized {} A2A client(s)", len(clients))
        yield client, clients
    finally:
        await client.aclose()


async def _discover_and_build_tools() -> tuple[list[BaseTool], list[AgentCard]]:
    """Discover agents and build LangChain tools for each one.

    Returns:
        A tuple of (tools list, agent cards list).
    """
    headers = {}
    id_token = get_id_token()
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    client = httpx.AsyncClient(
        timeout=httpx.Timeout(300, connect=30),
        headers=headers,
        limits=httpx.Limits(max_keepalive_connections=0),
    )
    try:
        resp = await client.get(f"{BASE_URL}/agents")
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, list):
            raise ValueError(f"Expected list of agent cards, got {type(data).__name__}")
        cards = [AgentCard(**card) for card in data]
        tools = []
        for card in cards:
            a2a_client = await ClientFactory.connect(
                card,
                client_config=ClientConfig(httpx_client=client),
            )
            tool_name = card.name.lower().replace(" ", "_")
            description = card.description or f"Talk to the {card.name} agent."
            tools.append(make_a2a_tool(tool_name, description, a2a_client))
        logger.info("Built {} dynamic tool(s): {}", len(tools), [t.name for t in tools])
        return tools, cards
    except Exception:
        await client.aclose()
        raise


def _build_system_prompt(cards: list[AgentCard]) -> str:
    """Build a system prompt listing available agents."""
    agent_lines = []
    for card in cards:
        tool_name = card.name.lower().replace(" ", "_")
        desc = card.description or card.name
        agent_lines.append(f"- {tool_name}: {desc}")
    agents_section = "\n".join(agent_lines)
    return (
        "You are a helpful assistant with access to the following agents:\n"
        f"{agents_section}\n\n"
        "Route user queries to the most appropriate agent. "
        "Always provide citations when applicable."
        f"Today's date is {datetime.now().date()}"
    )


# ---------------------------------------------------------------------------
# Orchestrator agent
# ---------------------------------------------------------------------------


async def get_agent() -> CompiledStateGraph:
    """Return the cached orchestrator agent, discovering tools dynamically."""
    if "agent" not in st.session_state:
        tools, cards = await _discover_and_build_tools()
        system_prompt = _build_system_prompt(cards)
        st.session_state.agent = create_agent(
            model,
            tools,
            system_prompt=system_prompt,
        )
        st.session_state.agent_cards = cards
    return st.session_state.agent


# ---------------------------------------------------------------------------
# Streaming agent execution
# ---------------------------------------------------------------------------


async def run_agent_stream(
    query: str, history: list[tuple[str, str]]
) -> AsyncGenerator[dict[str, str], None]:
    """Run the orchestrator agent and yield streaming events."""
    agent = await get_agent()
    async for raw_event in agent.astream_events(
        {"messages": history + [("user", query)]},
        version="v2",
    ):
        event = StreamEvent.model_validate(raw_event)

        if event.event == EventType.CHAT_MODEL_STREAM:
            chunk = event.data.get("chunk", {})
            content = (
                chunk.content if hasattr(chunk, "content") else chunk.get("content")
            )
            if content and isinstance(content, str):
                yield {"type": "text", "content": content}

        elif event.event == EventType.CUSTOM_EVENT:
            if event.name == CustomEventName.A2A_TOOL:
                data = event.data
                if data.get("type") == "tool_call":
                    tc = ToolCallData(**data)
                    yield {"type": "status", "content": f"Calling {tc.name}..."}
                elif data.get("type") == "tool_result":
                    tr = ToolResultData(**data)
                    yield {"type": "status", "content": f"{tr.name} returned results."}
            elif event.name == CustomEventName.A2A_STREAM:
                pass  # intermediate streaming text from agent, not shown directly

        elif event.event == EventType.TOOL_START:
            yield {"type": "status", "content": f"Using {event.name}..."}

        elif event.event == EventType.TOOL_END:
            yield {"type": "status", "content": f"{event.name} finished."}
