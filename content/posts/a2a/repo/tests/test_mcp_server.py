import pytest
import httpx
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware

from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore

from starlette.routing import Route

from mcp_server.auth import AzureADAuthBackend
from agents import get_wiki_agent, wikipedia_agent_card
from mcp_server.base import agent_cards, list_agent_cards
from mcp_server.text_executor import LangChainAgentExecutor


@pytest.fixture(autouse=True)
def _populate_agent_cards():
    agent_cards.clear()
    agent_cards.extend([wikipedia_agent_card])
    yield
    agent_cards.clear()


@pytest.fixture()
def app():
    starlette_app = Starlette(
        routes=[Route("/agents", list_agent_cards)],
        middleware=[Middleware(AuthenticationMiddleware, backend=AzureADAuthBackend())],
    )

    wiki_handler = DefaultRequestHandler(
        agent_executor=LangChainAgentExecutor(get_wiki_agent()),
        task_store=InMemoryTaskStore(),
    )
    A2AStarletteApplication(
        agent_card=wikipedia_agent_card,
        http_handler=wiki_handler,
    ).add_routes_to_app(
        starlette_app,
        agent_card_url="/.well-known/wikipedia-agent.json",
        rpc_url="/wikipedia",
    )

    return starlette_app


@pytest.fixture()
def client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


@pytest.mark.asyncio
async def test_wikipedia_agent_card(client):
    resp = await client.get("/.well-known/wikipedia-agent.json")
    assert resp.status_code == 200
    card = resp.json()
    assert card["name"] == "Wikipedia Agent"
    assert card["url"] == "http://localhost:9999/wikipedia"
    assert any(s["id"] == "wikipedia-search" for s in card["skills"])


@pytest.mark.asyncio
async def test_list_agents_endpoint(client):
    resp = await client.get("/agents")
    assert resp.status_code == 200
    cards = resp.json()
    assert len(cards) == 1
    names = {c["name"] for c in cards}
    assert names == {"Wikipedia Agent"}
