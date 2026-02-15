import asyncio

import httpx
from a2a.client.client import ClientConfig
from a2a.client.client_factory import ClientFactory
from a2a.types import AgentCard
from loguru import logger

from client.common import BASE_URL, make_a2a_tool

_httpx_client: httpx.AsyncClient | None = None
_a2a_tools: list | None = None
_client_lock: asyncio.Lock | None = None


def _get_lock() -> asyncio.Lock:
    global _client_lock
    if _client_lock is None:
        _client_lock = asyncio.Lock()
    return _client_lock


def get_httpx_client() -> httpx.AsyncClient:
    global _httpx_client
    if _httpx_client is None or _httpx_client.is_closed:
        _httpx_client = httpx.AsyncClient(
            timeout=httpx.Timeout(300, connect=30),
            limits=httpx.Limits(max_keepalive_connections=0),
        )
    return _httpx_client


async def _discover_agents() -> list[AgentCard]:
    """Fetch the list of available agents from the /agents endpoint."""
    client = get_httpx_client()
    logger.info("Discovering agents at {}/agents", BASE_URL)
    resp = await client.get(f"{BASE_URL}/agents")
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Expected list of agent cards, got {type(data).__name__}")
    cards = [AgentCard(**card) for card in data]
    logger.info("Discovered {} agent(s)", len(cards))
    return cards


async def get_tools() -> list:
    """Discover agents and create a LangChain tool for each one."""
    global _a2a_tools
    lock = _get_lock()
    async with lock:
        if _a2a_tools is None:
            client = get_httpx_client()
            cards = await _discover_agents()
            _a2a_tools = []
            for card in cards:
                logger.debug("Connecting to agent: {}", card.name)
                a2a_client = await ClientFactory.connect(
                    card,
                    client_config=ClientConfig(httpx_client=client),
                )
                tool_name = card.name.lower().replace(" ", "_")
                description = card.description or f"Talk to the {card.name} agent."
                _a2a_tools.append(make_a2a_tool(tool_name, description, a2a_client))
            logger.info(
                "Created {} tool(s): {}", len(_a2a_tools), [t.name for t in _a2a_tools]
            )
    return _a2a_tools
