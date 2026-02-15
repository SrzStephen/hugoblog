import asyncio

import httpx
import streamlit as st
from a2a.types import AgentCard

from client.streamlit_app.a2a_utils import (
    BASE_URL,
    http_client,
    run_agent_stream,
)
from client.streamlit_app.auth import (
    login_flow,
    can_call_agents,
    logout,
    get_user,
    get_id_token,
)
from loguru import logger


# ---------------------------------------------------------------------------
# Streamlit UI
# ---------------------------------------------------------------------------

st.set_page_config(page_title="A2A Chat", page_icon="🤖")
st.title("A2A Chat")

# Auth gate
if not login_flow():
    st.stop()

# Sidebar: user info + logout
user = get_user()
claims = user.get("id_token_claims", {})
st.sidebar.write(f"Signed in as: {claims.get('preferred_username', 'Unknown')}")

if st.sidebar.button("Sign out"):
    logout()

# Role gate
if not can_call_agents():
    roles = claims.get("roles", [])
    logger.warning(
        "User lacks agent.caller role. roles={}, claims={}", roles, list(claims.keys())
    )
    st.warning(
        "You do not have permission to use this application. "
        "Contact your administrator to assign you the 'Agent Caller' app role.\n\n"
        f"**Debug:** roles claim present: `{'roles' in claims}`, "
        f"role count: `{len(roles)}`"
    )
    st.stop()

# Initialize session state
if "messages" not in st.session_state:
    st.session_state.messages = []

# Try to connect to the mcp_server on startup (GET is unauthenticated)
try:
    headers = {}
    id_token = get_id_token()
    if id_token:
        headers["Authorization"] = f"Bearer {id_token}"
    resp = httpx.get(f"{BASE_URL}/agents", timeout=10, headers=headers)
    resp.raise_for_status()
    data = resp.json()
    if not isinstance(data, list):
        raise ValueError(f"Expected list of agent cards, got {type(data).__name__}")
    agent_cards = [AgentCard(**card) for card in data]
    logger.info("Connected to agent server at {}", BASE_URL)
except (httpx.ConnectError, httpx.TimeoutException) as exc:
    logger.error("Cannot connect to agent server at {}: {}", BASE_URL, exc)
    st.error(
        f"Cannot connect to agent server at {BASE_URL}. Please start the mcp_server first."
    )
    st.stop()
except httpx.HTTPStatusError as exc:
    logger.error("Agent server returned error: {}", exc)
    st.error(f"Agent server returned HTTP {exc.response.status_code}.")
    st.stop()
except (ValueError, KeyError) as exc:
    logger.error("Invalid response from agent server: {}", exc)
    st.error(f"Unexpected response from agent server: {exc}")
    st.stop()

# Sidebar: available agents
st.sidebar.markdown("---")
st.sidebar.subheader("Available Agents")
for card in agent_cards:
    st.sidebar.markdown(f"**{card.name}**")
    if card.description:
        st.sidebar.caption(card.description)

# Render chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        if msg.get("content"):
            st.markdown(msg["content"])

# Chat input
if user_input := st.chat_input("Ask me anything..."):
    # Display user message
    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    # Build conversation history for the agent
    history: list[tuple[str, str]] = []
    for msg in st.session_state.messages[:-1]:  # exclude the just-added user message
        if msg["role"] == "user":
            history.append(("user", msg["content"]))
        elif msg["role"] == "assistant" and msg.get("content"):
            history.append(("assistant", msg["content"]))

    # Stream the assistant response
    with st.chat_message("assistant"):
        text_placeholder = st.empty()
        status_placeholder = st.empty()
        state = {"text": ""}

        async def _run() -> None:
            async with http_client() as (_http_client, _clients):
                logger.info("Processing user input — length={}", len(user_input))
                async for event in run_agent_stream(user_input, history):
                    if event["type"] == "text":
                        state["text"] += event["content"]
                        text_placeholder.markdown(state["text"] + "▌")
                    elif event["type"] == "status":
                        status_placeholder.caption(event["content"])

        asyncio.run(_run())

        # Final render (remove cursor)
        text_placeholder.markdown(state["text"])
        status_placeholder.empty()

    # Save assistant message to history
    st.session_state.messages.append(
        {
            "role": "assistant",
            "content": state["text"],
        }
    )
