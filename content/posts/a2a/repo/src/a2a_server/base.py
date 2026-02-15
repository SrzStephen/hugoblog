import uvicorn
from dotenv import load_dotenv
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

load_dotenv()
from a2a.server.apps.jsonrpc.jsonrpc_app import CallContextBuilder
from a2a.server.apps.jsonrpc.starlette_app import A2AStarletteApplication
from a2a.server.context import ServerCallContext, User, UnauthenticatedUser
from a2a.server.request_handlers.default_request_handler import DefaultRequestHandler
from a2a.server.tasks.inmemory_task_store import InMemoryTaskStore
from a2a.types import AgentCard

from agents import (
    get_wiki_agent,
    wikipedia_agent_card,
    duck_agent_card,
    get_duck_agent,
    text_agent_card,
)
from a2a_server.auth import AGENT_CALLER_ROLE, AzureADAuthBackend, RequireAuthMiddleware
from a2a_server.text_executor import LangChainAgentExecutor, TextAgentExecutor
from loguru import logger
from util import get_route


# -- Auth context bridge -------------------------------------------------------


class StarletteUser(User):
    """Wraps a Starlette request.user as an A2A SDK User."""

    def __init__(self, starlette_user) -> None:
        self._user = starlette_user

    @property
    def is_authenticated(self) -> bool:
        return self._user.is_authenticated

    @property
    def user_name(self) -> str:
        return getattr(self._user, "display_name", "") or ""


class AuthCallContextBuilder(CallContextBuilder):
    """Bridges Starlette auth into ServerCallContext with roles in state."""

    def build(self, request: Request) -> ServerCallContext:
        starlette_user = request.user
        user: User
        roles: list[str] = []

        if starlette_user.is_authenticated:
            user = StarletteUser(starlette_user)
            claims = getattr(starlette_user, "claims", {})
            roles = claims.get("roles", [])
        else:
            user = UnauthenticatedUser()

        return ServerCallContext(
            user=user,
            state={"roles": roles},
        )


_context_builder = AuthCallContextBuilder()


# -- Agent cards ---------------------------------------------------------------

agent_cards: list[AgentCard] = []


async def list_agent_cards(request: Request) -> JSONResponse:
    roles = getattr(request.user, "claims", {}).get("roles", [])
    restricted_names = {duck_agent_card.name}
    visible = [
        c
        for c in agent_cards
        if c.name not in restricted_names or AGENT_CALLER_ROLE in roles
    ]
    logger.debug(
        "Agent discovery request received — returning {} card(s)", len(visible)
    )
    return JSONResponse(
        [card.model_dump(mode="json", exclude_none=True) for card in visible]
    )


def add_agent_route(app: Starlette, agent_card: AgentCard, agent) -> None:
    route = get_route(agent_card)
    handler = DefaultRequestHandler(
        agent_executor=LangChainAgentExecutor(agent),
        task_store=InMemoryTaskStore(),
    )
    A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
        context_builder=_context_builder,
    ).add_routes_to_app(
        app,
        agent_card_url=f"/.well-known{route}-agent.json",
        rpc_url=route,
    )


def add_text_agent_route(app: Starlette, agent_card: AgentCard) -> None:
    route = get_route(agent_card)
    handler = DefaultRequestHandler(
        agent_executor=TextAgentExecutor(),
        task_store=InMemoryTaskStore(),
    )
    A2AStarletteApplication(
        agent_card=agent_card,
        http_handler=handler,
        context_builder=_context_builder,
    ).add_routes_to_app(
        app,
        agent_card_url=f"/.well-known{route}-agent.json",
        rpc_url=route,
    )


# -- Server --------------------------------------------------------------------
def main() -> None:
    from util.config import configure_logging

    configure_logging()

    agent_cards.extend([wikipedia_agent_card, duck_agent_card, text_agent_card])
    for card in agent_cards:
        logger.info("Registered agent: name={}", card.name)
    app = Starlette(
        routes=[Route("/agents", list_agent_cards)],
        middleware=[
            Middleware(AuthenticationMiddleware, backend=AzureADAuthBackend()),
            Middleware(
                RequireAuthMiddleware,
                role_restricted_prefixes=[get_route(duck_agent_card)],
                open_prefixes=[
                    get_route(wikipedia_agent_card),
                    "/agents",
                    get_route(text_agent_card),
                ],
            ),
        ],
    )

    add_agent_route(app, wikipedia_agent_card, get_wiki_agent())
    add_agent_route(app, duck_agent_card, get_duck_agent())
    add_text_agent_route(app, text_agent_card)
    logger.info("Starting A2A server on 0.0.0.0:9999")
    uvicorn.run(app, host="0.0.0.0", port=9999)


if __name__ == "__main__":
    main()
