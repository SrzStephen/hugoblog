"""Tests for the Streamlit chat app utilities (src/client/streamlit_app/a2a_utils.py).

These tests exercise the pure-logic helpers and the streaming generator
without launching a real Streamlit server or connecting to the agent server.
"""

import sys
import uuid
from contextlib import asynccontextmanager
from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from a2a.types import (
    Artifact,
    Message,
    Part,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)


# ---------------------------------------------------------------------------
# Async iterable helpers for mocking
# ---------------------------------------------------------------------------
class AsyncIterableOf:
    """Wraps a list into an async iterable."""

    def __init__(self, items):
        self._items = list(items)

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self._items:
            raise StopAsyncIteration
        return self._items.pop(0)


class AsyncIterableOfFn:
    """Returns an async generator function suitable for patching astream_events."""

    def __init__(self, items):
        self._items = items

    def __call__(self, *args, **kwargs):
        items = list(self._items)

        async def gen():
            for item in items:
                yield item

        return gen()


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------
def _text_status_event(
    text: str, state: TaskState = TaskState.working
) -> TaskStatusUpdateEvent:
    return TaskStatusUpdateEvent(
        task_id="t1",
        context_id="ctx1",
        final=False,
        status=TaskStatus(
            state=state,
            message=Message(
                role="agent",
                message_id=str(uuid.uuid4()),
                parts=[Part(root=TextPart(text=text))],
            ),
        ),
    )


def _artifact_event(text: str) -> TaskArtifactUpdateEvent:
    return TaskArtifactUpdateEvent(
        task_id="t1",
        context_id="ctx1",
        artifact=Artifact(
            artifact_id="a1",
            parts=[Part(root=TextPart(text=text))],
        ),
    )


# ---------------------------------------------------------------------------
# Fixture: import the module with Streamlit and MSAL mocked out
# ---------------------------------------------------------------------------
class _AttrDict(dict):
    """Dict that supports attribute access (like Streamlit's session_state)."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            raise AttributeError(name)

    def __setattr__(self, name, value):
        self[name] = value

    def __delattr__(self, name):
        try:
            del self[name]
        except KeyError:
            raise AttributeError(name)


@pytest.fixture(autouse=True)
def _mock_streamlit_and_msal():
    """Patch Streamlit, MSAL, and extra_streamlit_components so the module can be imported without side effects."""
    mock_st = MagicMock()
    mock_st.session_state = _AttrDict()
    mock_st.query_params = {}
    mock_st.chat_input.return_value = None
    mock_st.stop.side_effect = None

    mock_msal = MagicMock()
    mock_stx = MagicMock()

    saved_modules = {}
    modules_to_mock = {
        "streamlit": mock_st,
        "msal": mock_msal,
        "extra_streamlit_components": mock_stx,
    }

    for mod_name, mock_mod in modules_to_mock.items():
        saved_modules[mod_name] = sys.modules.get(mod_name)
        sys.modules[mod_name] = mock_mod

    # Clear cached imports so reimport picks up mocks
    for mod_name in list(sys.modules):
        if mod_name.startswith("client.streamlit_app"):
            saved_modules[mod_name] = sys.modules.pop(mod_name)

    yield mock_st

    # Restore original modules
    for mod_name, original in saved_modules.items():
        if original is None:
            sys.modules.pop(mod_name, None)
        else:
            sys.modules[mod_name] = original


def _import_utils():
    """Import (or reimport) the a2a_utils module."""
    with patch("langchain.agents.create_agent", return_value=MagicMock()):
        import client.streamlit_app.a2a_utils as utils_mod

        return utils_mod


# ---------------------------------------------------------------------------
# _make_message
# ---------------------------------------------------------------------------
class TestMakeMessage:
    def test_returns_user_message_with_text(self):
        utils = _import_utils()
        msg = utils._make_message("hello world")
        assert msg.role == "user"
        assert len(msg.parts) == 1
        assert msg.parts[0].root.text == "hello world"
        uuid.UUID(msg.message_id)  # valid UUID


# ---------------------------------------------------------------------------
# _first_part
# ---------------------------------------------------------------------------
class TestFirstPart:
    def test_returns_first_part_from_status_event(self):
        utils = _import_utils()
        event = _text_status_event("some text")
        part = utils._first_part(event)
        assert isinstance(part, TextPart)
        assert part.text == "some text"

    def test_returns_none_for_empty_status(self):
        utils = _import_utils()
        event = TaskStatusUpdateEvent(
            task_id="t1",
            context_id="ctx1",
            final=False,
            status=TaskStatus(state=TaskState.working),
        )
        assert utils._first_part(event) is None


# ---------------------------------------------------------------------------
# call_a2a_agent / make_a2a_tool
# ---------------------------------------------------------------------------
class TestCallA2AAgent:
    @pytest.mark.asyncio
    async def test_returns_artifact_text(self):
        from client.common import call_a2a_agent

        artifact_event = _artifact_event("Python is a programming language.")

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(
            return_value=AsyncIterableOf([("id", artifact_event)])
        )

        result = await call_a2a_agent(mock_client, "Python")
        assert "Python is a programming language" in result

    @pytest.mark.asyncio
    async def test_returns_error_on_failed_state(self):
        from client.common import call_a2a_agent

        failed_event = _text_status_event(
            "Something went wrong", state=TaskState.failed
        )

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(
            return_value=AsyncIterableOf([("id", failed_event)])
        )

        result = await call_a2a_agent(mock_client, "bad query")
        assert "went wrong" in result or "failed" in result.lower()

    @pytest.mark.asyncio
    async def test_returns_no_results_when_empty(self):
        from client.common import call_a2a_agent

        working_event = _text_status_event("Searching...")

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(
            return_value=AsyncIterableOf([("id", working_event)])
        )

        with patch("client.common.adispatch_custom_event", new_callable=AsyncMock):
            result = await call_a2a_agent(mock_client, "obscure query")
            assert result == "No results found."


class TestMakeA2ATool:
    @pytest.mark.asyncio
    async def test_tool_calls_agent_and_returns_result(self):
        from client.common import make_a2a_tool

        artifact_event = _artifact_event("Duck facts are fun.")

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(
            return_value=AsyncIterableOf([("id", artifact_event)])
        )

        tool = make_a2a_tool("duck_agent", "Ask about ducks", mock_client)
        assert tool.name == "duck_agent"
        result = await tool.ainvoke("tell me about ducks")
        assert "Duck facts are fun" in result

    @pytest.mark.asyncio
    async def test_tool_returns_error_on_exception(self):
        from client.common import make_a2a_tool

        mock_client = MagicMock()
        mock_client.send_message = MagicMock(side_effect=ConnectionError("offline"))

        tool = make_a2a_tool("test_agent", "A test agent", mock_client)
        result = await tool.ainvoke("anything")
        assert "Error" in result or "failed" in result.lower()


# ---------------------------------------------------------------------------
# run_agent_stream
# ---------------------------------------------------------------------------
class TestRunAgentStream:
    @pytest.mark.asyncio
    async def test_yields_text_and_status_events(self):
        utils = _import_utils()

        chunk_mock = MagicMock()
        chunk_mock.content = "Hello"

        mock_agent = MagicMock()
        mock_agent.astream_events = AsyncIterableOfFn(
            [
                {
                    "event": "on_chat_model_stream",
                    "name": "model",
                    "data": {"chunk": chunk_mock},
                },
                {"event": "on_tool_start", "name": "duck_agent", "data": {}},
                {"event": "on_tool_end", "name": "duck_agent", "data": {}},
            ]
        )

        async def _mock_get_agent():
            return mock_agent

        with patch.object(utils, "get_agent", _mock_get_agent):
            events = []
            async for ev in utils.run_agent_stream("test query", []):
                events.append(ev)

        text_events = [e for e in events if e["type"] == "text"]
        status_events = [e for e in events if e["type"] == "status"]

        assert len(text_events) == 1
        assert text_events[0]["content"] == "Hello"
        assert len(status_events) == 2
        assert "duck_agent" in status_events[0]["content"]
