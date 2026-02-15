"""Microsoft Entra ID (Azure AD) authentication for the Streamlit app.

Uses MSAL Authorization Code Flow. App role membership is read from the
``roles`` claim in the ID token — no Graph API calls needed.

Auth state is persisted in a browser cookie so the user stays logged in
across page refreshes and new tabs.

Required environment variables:
    AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID,
    AZURE_REDIRECT_URI
"""

import time

import extra_streamlit_components as stx
import msal
import streamlit as st
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from loguru import logger

from util.settings import mysettings

CLIENT_ID = str(mysettings.entra.AZURE_CLIENT_ID)
CLIENT_SECRET = mysettings.entra.AZURE_CLIENT_SECRET.get_secret_value()
TENANT_ID = str(mysettings.entra.AZURE_TENANT_ID)
REDIRECT_URI = str(mysettings.entra.AZURE_REDIRECT_URI)
AGENT_CALLER_ROLE = mysettings.entra.AZURE_AGENT_CALLER_ROLE

AUTHORITY = f"https://login.microsoftonline.com/{TENANT_ID}"
SCOPES: list[str] = []  # only need an ID token

_AUTH_COOKIE = "a2a_auth"
_serializer = URLSafeTimedSerializer(CLIENT_SECRET)


@st.cache_resource
def _get_pending_flows() -> dict[str, dict]:
    """Module-level cache for auth flows, keyed by the OAuth ``state`` parameter.

    Using ``st.cache_resource`` so the dict survives Streamlit module reloads
    and session resets that happen during the redirect to Microsoft and back.
    """
    return {}


def _get_cookie_manager() -> stx.CookieManager:
    if "cookie_manager" not in st.session_state:
        st.session_state.cookie_manager = stx.CookieManager()
    return st.session_state.cookie_manager


def _get_msal_app() -> msal.ConfidentialClientApplication:
    if "msal_app" not in st.session_state:
        st.session_state.msal_app = msal.ConfidentialClientApplication(
            CLIENT_ID,
            authority=AUTHORITY,
            client_credential=CLIENT_SECRET,
        )
    return st.session_state.msal_app


def _save_auth_cookie(user_data: dict) -> None:
    """Persist signed auth data to a browser cookie."""
    cm = _get_cookie_manager()
    cookie_data = {
        "id_token": user_data.get("id_token"),
        "id_token_claims": user_data.get("id_token_claims"),
    }
    exp_claims = user_data.get("id_token_claims", {})
    exp = exp_claims.get("exp")
    max_age = int(exp - time.time()) if exp else 3600
    max_age = max(max_age, 0)
    signed = _serializer.dumps(cookie_data)
    cm.set(_AUTH_COOKIE, signed, max_age=max_age)
    logger.info("Saved signed auth cookie, max_age={}s", max_age)


def _load_auth_cookie() -> dict | None:
    """Try to restore auth data from a signed browser cookie."""
    cm = _get_cookie_manager()
    raw = cm.get(_AUTH_COOKIE)
    if not raw:
        return None
    try:
        data = _serializer.loads(raw)
        exp = data.get("id_token_claims", {}).get("exp")
        if exp and time.time() >= exp:
            logger.info("Auth cookie expired, discarding")
            cm.delete(_AUTH_COOKIE)
            return None
        return data
    except SignatureExpired:
        logger.info("Auth cookie signature expired, discarding")
        cm.delete(_AUTH_COOKIE)
        return None
    except BadSignature:
        logger.warning("Auth cookie has invalid signature, discarding")
        cm.delete(_AUTH_COOKIE)
        return None


def _clear_auth_cookie() -> None:
    cm = _get_cookie_manager()
    cm.delete(_AUTH_COOKIE)


def get_auth_url() -> str:
    app = _get_msal_app()
    flow = app.initiate_auth_code_flow(SCOPES, redirect_uri=REDIRECT_URI)
    pending = _get_pending_flows()
    pending[flow["state"]] = flow
    logger.info(
        "Created auth flow, state={}, pending_flows={}", flow["state"], len(pending)
    )
    return flow["auth_uri"]


def handle_auth_callback() -> bool:
    """Exchange the auth code in query params for tokens. Returns True on success."""
    params = dict(st.query_params)
    state = params.get("state")
    pending = _get_pending_flows()
    logger.info(
        "Auth callback — state={}, pending_flows keys={}", state, list(pending.keys())
    )

    flow = pending.get(state) if state else None
    if flow is None:
        logger.warning("No matching auth flow found for state={}", state)
        return False

    app = _get_msal_app()
    result = app.acquire_token_by_auth_code_flow(flow, params)

    # Only remove the flow after a successful exchange — the CookieManager
    # component can trigger an extra script rerun before st.rerun() fires,
    # so we need the flow to survive multiple runs within the same redirect.
    if "error" in result:
        logger.error("MSAL token exchange failed: {}", result)
        st.error(
            f"Authentication failed: {result.get('error_description', result['error'])}"
        )
        return False

    pending.pop(state, None)
    logger.info(
        "Authentication successful, claims keys={}",
        list(result.get("id_token_claims", {}).keys()),
    )
    st.session_state.user = result
    _save_auth_cookie(result)
    st.query_params.clear()
    return True


def _is_token_expired() -> bool:
    """Check whether the ID token has expired."""
    claims = get_user().get("id_token_claims", {})
    exp = claims.get("exp")
    if exp is None:
        return True
    return time.time() >= exp


def login_flow() -> bool:
    """Orchestrate login. Returns True if the user is authenticated."""
    # 1. Check session state first (no components needed)
    if "user" in st.session_state:
        if _is_token_expired():
            logger.warning("ID token expired, clearing session")
            st.session_state.pop("user", None)
            st.session_state.pop("msal_app", None)
            _clear_auth_cookie()
        else:
            return True

    # 2. Handle OAuth callback (must run before cookie check to avoid interference)
    if "code" in st.query_params:
        if handle_auth_callback():
            st.rerun()
        # Callback failed — show error and sign-in link (don't rerun,
        # so the user can see what went wrong).
        st.query_params.clear()

    # 3. Initialise the CookieManager and ensure its JS component has had a
    #    render cycle to load.  The first time it mounts it triggers a
    #    Streamlit rerun; if we show the login link before that rerun the
    #    user's click can be swallowed by the page refresh.
    _get_cookie_manager()
    if not st.session_state.get("_cookie_mgr_ready"):
        st.session_state._cookie_mgr_ready = True
        st.rerun()

    # 4. Try to restore from cookie (CookieManager is now ready)
    cookie_data = _load_auth_cookie()
    if cookie_data:
        logger.info("Restored session from cookie")
        st.session_state.user = cookie_data
        return True

    url = get_auth_url()
    st.markdown(
        f'<a href="{url}" target="_self" style="font-size:1.2em;">'
        f"Sign in with Microsoft</a>",
        unsafe_allow_html=True,
    )
    return False


def get_user() -> dict:
    return st.session_state.get("user", {})


def get_id_token() -> str | None:
    """Return the raw ID token JWT string, or None if not authenticated."""
    return get_user().get("id_token")


def can_call_agents() -> bool:
    user = get_user()
    roles = user.get("id_token_claims", {}).get("roles", [])
    return AGENT_CALLER_ROLE in roles


def logout() -> None:
    _clear_auth_cookie()
    st.session_state.pop("user", None)
    st.session_state.pop("msal_app", None)
    st.rerun()
