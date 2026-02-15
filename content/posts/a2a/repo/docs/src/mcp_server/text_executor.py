import asyncio
import uuid
from collections import defaultdict

import httpx
from a2a.server.agent_execution import RequestContext, AgentExecutor
from a2a.server.events import EventQueue
from a2a.types import (
    Part,
    DataPart,
    TaskState,
    TextPart,
    Message,
    TaskStatusUpdateEvent,
    TaskStatus,
    TaskArtifactUpdateEvent,
    Artifact,
)
from loguru import logger
from mcp_server.types import EventType, StreamEvent, ToolCallData, ToolResultData


class LangChainAgentExecutor(AgentExecutor):
    """Base executor that bridges a LangChain agent to the A2A protocol."""

    def __init__(self, agent) -> None:
        self._agent = agent
        self._conversation_history: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self._running_tasks: dict[str, asyncio.Task] = {}

    async def _send_status(
        self,
        event_queue: EventQueue,
        context: RequestContext,
        state: TaskState,
        *,
        final: bool = False,
        text: str | None = None,
        parts: list[Part] | None = None,
    ) -> None:
        message = None
        if text is not None:
            parts = [Part(root=TextPart(text=text))]
        if parts is not None:
            message = Message(
                role="agent",
                message_id=str(uuid.uuid4()),
                parts=parts,
            )
        await event_queue.enqueue_event(
            TaskStatusUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                final=final,
                status=TaskStatus(state=state, message=message),
            )
        )

    async def _send_artifact(
        self,
        event_queue: EventQueue,
        context: RequestContext,
        parts: list[Part],
    ) -> None:
        await event_queue.enqueue_event(
            TaskArtifactUpdateEvent(
                task_id=context.task_id,
                context_id=context.context_id,
                artifact=Artifact(
                    artifact_id=str(uuid.uuid4()),
                    parts=parts,
                ),
            )
        )

    async def _handle_custom_event(
        self,
        event: StreamEvent,
        event_queue: EventQueue,
        context: RequestContext,
    ) -> None:
        """Override in subclasses to handle custom LangChain events."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        user_text = context.get_user_input()
        logger.info(
            "execute() called — task_id={}, input_length={}",
            context.task_id,
            len(user_text) if user_text else 0,
        )
        if user_text:
            logger.debug("Input text (truncated): {}", user_text[:200])
        if not user_text:
            logger.warning("Received empty user input for task %s", context.task_id)
            await self._send_status(
                event_queue,
                context,
                TaskState.failed,
                final=True,
                text="No input provided.",
            )
            return

        task = asyncio.current_task()
        if task is not None:
            self._running_tasks[context.task_id] = task

        await self._send_status(event_queue, context, TaskState.working)

        context_id = context.context_id or context.task_id
        self._conversation_history[context_id].append(("user", user_text))

        failed = False
        canceled = False
        accumulated_text = ""

        try:
            async for event in self._agent.astream_events(
                {"messages": list(self._conversation_history[context_id])}, version="v2"
            ):
                event = StreamEvent(**event)
                if event.event == EventType.TOOL_START:
                    logger.info(
                        "Tool start: name={}, input={}",
                        event.name,
                        event.data.get("input", {}),
                    )
                    await self._send_status(
                        event_queue,
                        context,
                        TaskState.working,
                        parts=[
                            Part(
                                root=DataPart(
                                    data=ToolCallData(
                                        name=event.name,
                                        input=event.data.get("input", {}),
                                    ).model_dump()
                                )
                            )
                        ],
                    )
                elif event.event == EventType.TOOL_END:
                    logger.info("Tool end: name={}", event.name)
                    await self._send_status(
                        event_queue,
                        context,
                        TaskState.working,
                        parts=[
                            Part(
                                root=DataPart(
                                    data=ToolResultData(
                                        name=event.name,
                                        output=str(event.data.get("output", "")),
                                    ).model_dump()
                                )
                            )
                        ],
                    )
                elif event.event == EventType.CUSTOM_EVENT:
                    logger.debug("Custom event: name={}", event.name)
                    await self._handle_custom_event(event, event_queue, context)
                elif event.event == EventType.CHAT_MODEL_STREAM:
                    chunk = event.data.get("chunk", {})
                    content = (
                        chunk.content
                        if hasattr(chunk, "content")
                        else chunk.get("content")
                    )
                    if content and isinstance(content, str):
                        accumulated_text += content
                        await self._send_status(
                            event_queue,
                            context,
                            TaskState.working,
                            text=content,
                        )
        except asyncio.CancelledError:
            logger.info("Task cancelled for task_id={}", context.task_id)
            canceled = True
        except (
            httpx.ConnectError,
            httpx.TimeoutException,
            httpx.HTTPStatusError,
        ) as exc:
            logger.error(
                "Network error during agent execution for task %s: %s",
                context.task_id,
                exc,
            )
            failed = True
            if not accumulated_text:
                accumulated_text = f"{type(exc).__name__}: {exc}"
        except Exception as exc:
            logger.exception("Agent execution failed for task %s", context.task_id)
            failed = True
            if not accumulated_text:
                accumulated_text = f"{type(exc).__name__}: {exc}"
        finally:
            self._running_tasks.pop(context.task_id, None)

        if canceled:
            await self._send_status(
                event_queue,
                context,
                TaskState.canceled,
                final=True,
            )
            return

        if accumulated_text and not failed:
            self._conversation_history[context_id].append(
                ("assistant", accumulated_text)
            )

        if accumulated_text:
            await self._send_artifact(
                event_queue, context, [Part(root=TextPart(text=accumulated_text))]
            )

        final_state = TaskState.failed if failed else TaskState.completed
        logger.info(
            "execute() complete — task_id={}, state={}, response_length={}",
            context.task_id,
            final_state.value,
            len(accumulated_text),
        )
        await self._send_status(
            event_queue,
            context,
            final_state,
            final=True,
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        running_task = self._running_tasks.get(context.task_id)
        if running_task is not None:
            logger.info("Cancel requested for task_id={}", context.task_id)
            running_task.cancel()
        else:
            logger.warning(
                "Cancel requested but no matching task found — task_id={}",
                context.task_id,
            )
            await self._send_status(
                event_queue,
                context,
                TaskState.canceled,
                final=True,
            )


class TextAgentExecutor(LangChainAgentExecutor):
    """Executor that builds a per-request text agent with row-level access control."""

    def __init__(self) -> None:
        super().__init__(agent=None)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        from agents.text_agent.agent import get_text_agent

        call_ctx = context.call_context
        is_authenticated = False
        roles: list[str] = []

        if call_ctx:
            is_authenticated = call_ctx.user.is_authenticated
            roles = call_ctx.state.get("roles", [])

        logger.info(
            "TextAgentExecutor — authenticated={}, roles={}",
            is_authenticated,
            roles,
        )
        self._agent = get_text_agent(is_authenticated, roles)
        await super().execute(context, event_queue)
