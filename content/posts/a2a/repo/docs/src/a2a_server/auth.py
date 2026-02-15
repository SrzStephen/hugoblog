"""Azure AD JWT validation middleware for the A2A server.

Validates Bearer tokens (Azure AD ID tokens) on incoming requests.
GET requests are allowed through unauthenticated (agent discovery).
POST requests require a valid token.

Required environment variables:
    AZURE_CLIENT_ID, AZURE_TENANT_ID
"""

import time

import httpx
import jwt
from jwt.algorithms import RSAAlgorithm
from loguru import logger
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    BaseUser,
)
from starlette.requests import HTTPConnection
from starlette.requests import Request
from starlette.responses import JSONResponse

from util.settings import mysettings

CLIENT_ID = str(mysettings.entra.AZURE_CLIENT_ID)
TENANT_ID = str(mysettings.entra.AZURE_TENANT_ID)
AGENT_CALLER_ROLE = mysettings.entra.AZURE_AGENT_CALLER_ROLE

ISSUER = f"https://login.microsoftonline.com/{TENANT_ID}/v2.0"
JWKS_URI = f"https://login.microsoftonline.com/{TENANT_ID}/discovery/v2.0/keys"

# JWKS key cache (refreshed every hour)
_jwks_cache: dict = {"keys": None, "fetched_at": 0.0}


def _get_jwks() -> dict:
    if _jwks_cache["keys"] and time.time() - _jwks_cache["fetched_at"] < 3600:
        return _jwks_cache["keys"]
    logger.info("Fetching JWKS from {}", JWKS_URI)
    resp = httpx.get(JWKS_URI, timeout=10)
    resp.raise_for_status()
    jwks = resp.json()
    _jwks_cache["keys"] = jwks
    _jwks_cache["fetched_at"] = time.time()
    return jwks


def validate_token(token: str) -> dict | None:
    """Validate an Azure AD JWT and return its claims, or None on failure."""
    try:
        header = jwt.get_unverified_header(token)
        jwks = _get_jwks()

        key = None
        for k in jwks["keys"]:
            if k["kid"] == header.get("kid"):
                key = RSAAlgorithm.from_jwk(k)
                break
        if key is None:
            logger.warning("No matching JWK kid={}", header.get("kid"))
            return None

        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=CLIENT_ID,
            issuer=ISSUER,
        )
        return claims
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        return None
    except jwt.InvalidTokenError as e:
        logger.warning("Invalid token: {}", e)
        return None


class AzureADUser(BaseUser):
    """Starlette-compatible user populated from Azure AD token claims."""

    def __init__(self, claims: dict) -> None:
        self._claims = claims

    @property
    def is_authenticated(self) -> bool:
        return True

    @property
    def display_name(self) -> str:
        return self._claims.get("preferred_username", "")

    @property
    def claims(self) -> dict:
        return self._claims


class AzureADAuthBackend(AuthenticationBackend):
    """Starlette auth backend that validates Azure AD Bearer tokens."""

    async def authenticate(
        self, conn: HTTPConnection
    ) -> tuple[AuthCredentials, AzureADUser] | None:
        auth_header = conn.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return None

        token = auth_header.removeprefix("Bearer ")
        claims = validate_token(token)
        if claims is None:
            return None

        return AuthCredentials(["authenticated"]), AzureADUser(claims)


class RequireAuthMiddleware:
    """ASGI middleware that returns 401 for unauthenticated POST requests
    and 403 for requests to role-restricted paths without the required app role."""

    def __init__(
        self,
        app,
        role_restricted_prefixes: list[str] | None = None,
        open_prefixes: list[str] | None = None,
    ) -> None:
        self.app = app
        self.role_restricted_prefixes = role_restricted_prefixes or []
        self.open_prefixes = open_prefixes or []

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] == "http" and scope["method"] == "POST":
            path = scope.get("path", "")

            # Skip auth entirely for open prefixes
            if any(path.startswith(p) for p in self.open_prefixes):
                await self.app(scope, receive, send)
                return

            request = Request(scope)
            if not request.user.is_authenticated:
                response = JSONResponse(
                    {"error": "Authentication required"}, status_code=401
                )
                await response(scope, receive, send)
                return

            if any(path.startswith(p) for p in self.role_restricted_prefixes):
                roles = request.user.claims.get("roles", [])
                if AGENT_CALLER_ROLE not in roles:
                    response = JSONResponse(
                        {"error": "Forbidden — missing required app role"},
                        status_code=403,
                    )
                    await response(scope, receive, send)
                    return

        await self.app(scope, receive, send)
