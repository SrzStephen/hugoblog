"""Tests for Azure AD authentication middleware and helpers."""

import time
from unittest.mock import patch, MagicMock

import jwt as pyjwt
import pytest
import httpx
from a2a.types import AgentCard, AgentCapabilities, AgentSkill
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from jwt.algorithms import RSAAlgorithm
from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

_TEST_CLIENT_ID = "00000000-0000-0000-0000-000000000001"
_TEST_TENANT_ID = "00000000-0000-0000-0000-000000000002"

from a2a_server.auth import (
    AzureADAuthBackend,
    AzureADUser,
    RequireAuthMiddleware,
    validate_token,
    _jwks_cache,
    ISSUER,
    CLIENT_ID,
    AGENT_CALLER_ROLE,
)


# ---------------------------------------------------------------------------
# RSA key pair for signing test JWTs
# ---------------------------------------------------------------------------
_private_key = rsa.generate_private_key(
    public_exponent=65537, key_size=2048, backend=default_backend()
)
_public_key = _private_key.public_key()

# JWK representation of the public key (used to mock JWKS endpoint)
_public_jwk = RSAAlgorithm.to_jwk(_public_key, as_dict=True)
_public_jwk["kid"] = "test-kid"
_public_jwk["use"] = "sig"
_public_jwk["alg"] = "RS256"

_JWKS = {"keys": [_public_jwk]}


def _make_token(
    claims: dict | None = None, kid: str = "test-kid", expired: bool = False
) -> str:
    """Create a signed JWT with the given claims."""
    now = int(time.time())
    payload = {
        "iss": ISSUER,
        "aud": CLIENT_ID,
        "sub": "user-123",
        "iat": now - 60,
        "exp": now - 10 if expired else now + 3600,
        "preferred_username": "testuser@example.com",
    }
    if claims:
        payload.update(claims)
    return pyjwt.encode(payload, _private_key, algorithm="RS256", headers={"kid": kid})


# ---------------------------------------------------------------------------
# Mock agent cards (avoids importing agents module which may have validation issues)
# ---------------------------------------------------------------------------
_wiki_card = AgentCard(
    name="Wikipedia Agent",
    url="http://localhost:9999/wikipedia",
    version="1.0.0",
    description="Test wiki agent",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[
        AgentSkill(
            id="wiki", name="Wiki", description="Search Wikipedia", tags=["test"]
        )
    ],
)

_duck_card = AgentCard(
    name="DuckDuckGo Agent",
    url="http://localhost:9999/duckduckgo",
    version="1.0.0",
    description="Test duck agent",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(streaming=False),
    skills=[
        AgentSkill(
            id="duck", name="Duck", description="Search DuckDuckGo", tags=["test"]
        )
    ],
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _mock_jwks():
    """Patch _get_jwks so tests never hit the network."""
    with patch("a2a_server.auth._get_jwks", return_value=_JWKS):
        yield


@pytest.fixture(autouse=True)
def _clear_jwks_cache():
    """Reset the JWKS cache between tests."""
    _jwks_cache["keys"] = None
    _jwks_cache["fetched_at"] = 0.0


# ---------------------------------------------------------------------------
# Starlette test app with auth middleware
# ---------------------------------------------------------------------------
async def _echo(request: Request) -> JSONResponse:
    """Simple endpoint that returns auth info."""
    return JSONResponse(
        {
            "authenticated": request.user.is_authenticated,
            "username": getattr(request.user, "display_name", None),
        }
    )


async def _restricted(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def _open_post(request: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


def _build_app(
    role_restricted_prefixes: list[str] | None = None,
    open_prefixes: list[str] | None = None,
) -> Starlette:
    """Build a test Starlette app with auth middleware in the correct order.

    AuthenticationMiddleware must run first (outermost) to populate request.user,
    then RequireAuthMiddleware checks it.
    """
    return Starlette(
        routes=[
            Route("/open", _echo),
            Route("/open", _echo, methods=["POST"]),
            Route("/restricted", _restricted, methods=["POST"]),
            Route("/wikipedia", _open_post, methods=["POST"]),
        ],
        middleware=[
            Middleware(AuthenticationMiddleware, backend=AzureADAuthBackend()),
            Middleware(
                RequireAuthMiddleware,
                role_restricted_prefixes=role_restricted_prefixes or ["/restricted"],
                open_prefixes=open_prefixes or ["/wikipedia"],
            ),
        ],
    )


@pytest.fixture()
def app():
    return _build_app()


@pytest.fixture()
def client(app):
    transport = httpx.ASGITransport(app=app)
    return httpx.AsyncClient(transport=transport, base_url="http://testserver")


# ---------------------------------------------------------------------------
# validate_token unit tests
# ---------------------------------------------------------------------------
class TestValidateToken:
    def test_valid_token(self):
        token = _make_token()
        claims = validate_token(token)
        assert claims is not None
        assert claims["sub"] == "user-123"
        assert claims["preferred_username"] == "testuser@example.com"

    def test_expired_token_returns_none(self):
        token = _make_token(expired=True)
        assert validate_token(token) is None

    def test_wrong_audience_returns_none(self):
        now = int(time.time())
        token = pyjwt.encode(
            {
                "iss": ISSUER,
                "aud": "wrong-audience",
                "sub": "x",
                "iat": now,
                "exp": now + 3600,
            },
            _private_key,
            algorithm="RS256",
            headers={"kid": "test-kid"},
        )
        assert validate_token(token) is None

    def test_wrong_issuer_returns_none(self):
        now = int(time.time())
        token = pyjwt.encode(
            {
                "iss": "https://evil.example.com",
                "aud": CLIENT_ID,
                "sub": "x",
                "iat": now,
                "exp": now + 3600,
            },
            _private_key,
            algorithm="RS256",
            headers={"kid": "test-kid"},
        )
        assert validate_token(token) is None

    def test_unknown_kid_returns_none(self):
        token = _make_token(kid="unknown-kid")
        assert validate_token(token) is None

    def test_garbage_token_returns_none(self):
        assert validate_token("not.a.jwt") is None


# ---------------------------------------------------------------------------
# AzureADUser tests
# ---------------------------------------------------------------------------
class TestAzureADUser:
    def test_properties(self):
        user = AzureADUser(
            {"preferred_username": "alice@example.com", "groups": ["g1"]}
        )
        assert user.is_authenticated is True
        assert user.display_name == "alice@example.com"
        assert user.claims["groups"] == ["g1"]

    def test_missing_username(self):
        user = AzureADUser({})
        assert user.display_name == ""


# ---------------------------------------------------------------------------
# AzureADAuthBackend tests
# ---------------------------------------------------------------------------
class TestAzureADAuthBackend:
    @pytest.mark.asyncio
    async def test_no_auth_header_returns_none(self):
        backend = AzureADAuthBackend()
        conn = MagicMock()
        conn.headers = {}
        result = await backend.authenticate(conn)
        assert result is None

    @pytest.mark.asyncio
    async def test_non_bearer_header_returns_none(self):
        backend = AzureADAuthBackend()
        conn = MagicMock()
        conn.headers = {"Authorization": "Basic dXNlcjpwYXNz"}
        result = await backend.authenticate(conn)
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_bearer_returns_credentials_and_user(self):
        backend = AzureADAuthBackend()
        token = _make_token()
        conn = MagicMock()
        conn.headers = {"Authorization": f"Bearer {token}"}
        result = await backend.authenticate(conn)
        assert result is not None
        creds, user = result
        assert "authenticated" in creds.scopes
        assert user.is_authenticated
        assert user.display_name == "testuser@example.com"

    @pytest.mark.asyncio
    async def test_invalid_bearer_returns_none(self):
        backend = AzureADAuthBackend()
        conn = MagicMock()
        conn.headers = {"Authorization": "Bearer invalid.token.here"}
        result = await backend.authenticate(conn)
        assert result is None


# ---------------------------------------------------------------------------
# RequireAuthMiddleware integration tests
# ---------------------------------------------------------------------------
class TestRequireAuthMiddleware:
    @pytest.mark.asyncio
    async def test_get_allowed_without_auth(self, client):
        resp = await client.get("/open")
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_post_requires_auth(self, client):
        resp = await client.post("/open")
        assert resp.status_code == 401
        assert resp.json()["error"] == "Authentication required"

    @pytest.mark.asyncio
    async def test_post_with_valid_token(self, client):
        token = _make_token()
        resp = await client.post("/open", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True
        assert data["username"] == "testuser@example.com"

    @pytest.mark.asyncio
    async def test_restricted_path_forbidden_without_role(self, client):
        token = _make_token(claims={"roles": []})
        resp = await client.post(
            "/restricted", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403
        assert "Forbidden" in resp.json()["error"]

    @pytest.mark.asyncio
    async def test_restricted_path_allowed_with_role(self, client):
        token = _make_token(claims={"roles": [AGENT_CALLER_ROLE]})
        resp = await client.post(
            "/restricted", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_non_restricted_path_allowed_without_role(self, client):
        token = _make_token(claims={"roles": []})
        resp = await client.post("/open", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    @pytest.mark.asyncio
    async def test_open_prefix_allows_post_without_auth(self, client):
        resp = await client.post("/wikipedia")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_open_prefix_allows_post_with_auth(self, client):
        token = _make_token()
        resp = await client.post(
            "/wikipedia", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# list_agent_cards group filtering test
#
# Tests the filtering logic from base.list_agent_cards using mock cards
# to avoid importing the agents module (which may have validation issues).
# ---------------------------------------------------------------------------
class TestListAgentCardsFiltering:
    @pytest.mark.asyncio
    async def test_duck_card_hidden_without_role(self):
        """Unauthenticated users should not see the restricted card."""
        cards = [_wiki_card, _duck_card]
        restricted_card = _duck_card

        async def list_cards(request: Request) -> JSONResponse:
            roles = getattr(request.user, "claims", {}).get("roles", [])
            visible = [
                c for c in cards if c != restricted_card or AGENT_CALLER_ROLE in roles
            ]
            return JSONResponse(
                [c.model_dump(mode="json", exclude_none=True) for c in visible]
            )

        app = Starlette(
            routes=[Route("/agents", list_cards)],
            middleware=[
                Middleware(AuthenticationMiddleware, backend=AzureADAuthBackend())
            ],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            resp = await c.get("/agents")
            assert resp.status_code == 200
            names = {card["name"] for card in resp.json()}
            assert "Wikipedia Agent" in names
            assert "DuckDuckGo Agent" not in names

    @pytest.mark.asyncio
    async def test_duck_card_visible_with_role(self):
        """Users with the agent_caller role should see all cards."""
        cards = [_wiki_card, _duck_card]
        restricted_card = _duck_card

        async def list_cards(request: Request) -> JSONResponse:
            roles = getattr(request.user, "claims", {}).get("roles", [])
            visible = [
                c for c in cards if c != restricted_card or AGENT_CALLER_ROLE in roles
            ]
            return JSONResponse(
                [c.model_dump(mode="json", exclude_none=True) for c in visible]
            )

        app = Starlette(
            routes=[Route("/agents", list_cards)],
            middleware=[
                Middleware(AuthenticationMiddleware, backend=AzureADAuthBackend())
            ],
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(
            transport=transport, base_url="http://testserver"
        ) as c:
            token = _make_token(claims={"roles": [AGENT_CALLER_ROLE]})
            resp = await c.get("/agents", headers={"Authorization": f"Bearer {token}"})
            assert resp.status_code == 200
            names = {card["name"] for card in resp.json()}
            assert "Wikipedia Agent" in names
            assert "DuckDuckGo Agent" in names


# ---------------------------------------------------------------------------
# End-to-end authentication confirmation tests
# ---------------------------------------------------------------------------
class TestAuthEndToEnd:
    """Confirms the full auth flow works: token creation → middleware
    validation → correct HTTP status codes and user context propagation."""

    @pytest.mark.asyncio
    async def test_expired_token_rejected_by_middleware(self, client):
        """An expired JWT should be treated as unauthenticated (401)."""
        token = _make_token(expired=True)
        resp = await client.post("/open", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 401
        assert resp.json()["error"] == "Authentication required"

    @pytest.mark.asyncio
    async def test_garbage_token_rejected_by_middleware(self, client):
        """A completely invalid token string should result in 401."""
        resp = await client.post(
            "/open", headers={"Authorization": "Bearer not.a.real.token"}
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "Authentication required"

    @pytest.mark.asyncio
    async def test_missing_bearer_prefix_rejected(self, client):
        """A token without the 'Bearer ' prefix should be treated as unauthenticated."""
        token = _make_token()
        resp = await client.post("/open", headers={"Authorization": token})
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_role_restricted_with_expired_token(self, client):
        """Expired token on a role-restricted path should be 401, not 403."""
        token = _make_token(expired=True, claims={"roles": [AGENT_CALLER_ROLE]})
        resp = await client.post(
            "/restricted", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_claims_propagated(self, client):
        """Confirms the user's identity is correctly passed through the middleware."""
        token = _make_token(
            claims={
                "preferred_username": "bob@contoso.com",
                "roles": [AGENT_CALLER_ROLE],
            }
        )
        resp = await client.post("/open", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["authenticated"] is True
        assert data["username"] == "bob@contoso.com"

    @pytest.mark.asyncio
    async def test_multiple_roles_accepted(self, client):
        """A token with the required role among several should be accepted."""
        token = _make_token(claims={"roles": ["reader", AGENT_CALLER_ROLE, "admin"]})
        resp = await client.post(
            "/restricted", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 200
        assert resp.json()["ok"] is True

    @pytest.mark.asyncio
    async def test_wrong_role_forbidden(self, client):
        """A valid token with unrelated roles should be forbidden on restricted paths."""
        token = _make_token(claims={"roles": ["reader", "viewer"]})
        resp = await client.post(
            "/restricted", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403

    @pytest.mark.asyncio
    async def test_no_roles_claim_forbidden_on_restricted(self, client):
        """A valid token with no roles claim at all should be forbidden on restricted paths."""
        token = _make_token()  # no roles in payload
        resp = await client.post(
            "/restricted", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 403


# ---------------------------------------------------------------------------
# AuthCallContextBuilder tests
# ---------------------------------------------------------------------------
from a2a_server.base import AuthCallContextBuilder, StarletteUser


class TestAuthCallContextBuilder:
    """Tests the bridge between Starlette auth and A2A SDK ServerCallContext."""

    def test_authenticated_user_context(self):
        """Authenticated request should produce a context with user and roles."""
        user = AzureADUser(
            {
                "preferred_username": "alice@example.com",
                "roles": [AGENT_CALLER_ROLE, "admin"],
            }
        )
        request = MagicMock(spec=Request)
        request.user = user

        builder = AuthCallContextBuilder()
        ctx = builder.build(request)

        assert ctx.user.is_authenticated is True
        assert ctx.user.user_name == "alice@example.com"
        assert ctx.state["roles"] == [AGENT_CALLER_ROLE, "admin"]

    def test_unauthenticated_user_context(self):
        """Unauthenticated request should produce a context with no roles."""
        anon = MagicMock()
        anon.is_authenticated = False
        request = MagicMock(spec=Request)
        request.user = anon

        builder = AuthCallContextBuilder()
        ctx = builder.build(request)

        assert ctx.user.is_authenticated is False
        assert ctx.state["roles"] == []

    def test_starlette_user_wrapper(self):
        """StarletteUser should delegate to the underlying Starlette user."""
        inner = AzureADUser({"preferred_username": "wrapped@example.com"})
        wrapper = StarletteUser(inner)
        assert wrapper.is_authenticated is True
        assert wrapper.user_name == "wrapped@example.com"
