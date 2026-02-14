---
title: "Distributed Tracing: traceparent and LangChain"
date: 2026-02-08
draft: false
tags: ["observability"]
---


While doing some work to patch a hidden parameter into a FastMCP server for the purpose of tracing, I found
out that there was already a W3 spec that covered off a [traceparent header](https://www.w3.org/TR/trace-context/#traceparent-header)
as a formalised method to send parent headers over http boundaries.

```zsh
traceparent: 00-<trace_id>-<span_id>-<flags>                                                                                                                                                                                     
            │    │           │        └─ 01 = sampled                                                                                                                                                                        
            │    │           └─ 16-byte hex parent span id
            │    └─ 32-byte hex trace id
            └─ version
```
As this is a standard header you can expect to see common http client libraries have auto-instrumentation libraries such
as ([opentelemetry-instrumentation-httpx](https://pypi.org/project/opentelemetry-instrumentation-httpx/) for httpx
(the underlying http client library used for LangChains HTTP MCP implementation)
as well as
[opentelemetry-instrumentation-starlette](https://opentelemetry-python-contrib.readthedocs.io/en/latest/instrumentation/starlette/starlette.html)) 
for Starlette (the underlying library for FastMCPs server implementation).

# Doing it manually.
To test my understanding of how pythons otel library worked I tried instrumenting this manually:

## Client
```python
import httpx
from opentelemetry.trace import SpanKind
from opentelemetry import trace as trace_api
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider, Tracer
from opentelemetry.propagate import inject
from opentelemetry.sdk.trace.export import (
    SimpleSpanProcessor,
    ConsoleSpanExporter,
)
_original_async_send = httpx.AsyncClient.send


def _ensure_provider(service_name: str) -> TracerProvider:
    """Set up the global TracerProvider once per process."""
    if isinstance(trace_api.get_tracer_provider(), TracerProvider):
        return trace_api.get_tracer_provider()

    resource = Resource.create({"service.name": service_name})
    tracer_provider = TracerProvider(resource=resource)
    trace_api.set_tracer_provider(tracer_provider)
    tracer_provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
    return tracer_provider

def get_tracer_with_name(service_name: str, tracer_name: str) -> Tracer:
    _ensure_provider(service_name)
    return trace_api.get_tracer(tracer_name)

tracer = get_tracer_with_name("my-client",__name__)
stack_list = [] # assume you have something recording stacks


async def _propagating_send(self, request, **kwargs):
    url = request.url
    with tracer.start_as_current_span(
        f"{request.method} {url.host}",
        kind=SpanKind.CLIENT,
        context=stack_list[-1] if len(stack_list) != 0 else None
    ) as span:
        inject(request.headers)
        response = await _original_async_send(self, request, **kwargs)
        span.set_attribute("http.response.status_code", response.status_code)
        return response
    
httpx.AsyncClient.send = _propagating_send
```

## Server
Re-using `get_tracer_with_name` from the client
```python
from fastmcp import FastMCP
from fastmcp.server.dependencies import get_http_headers
from opentelemetry import context, propagate
from opentelemetry.trace import SpanKind
from .previous_demo import get_tracer_with_name

tracer = get_tracer_with_name(service="mcp-server",trace=__name__)
def _extract_trace_context():
    headers = get_http_headers(include_all=True)
    traceparent = headers.get("traceparent")
    if not traceparent:
        return context.get_current()
    return propagate.extract(carrier=headers)

mcp = FastMCP("My MCP Server")

@mcp.tool(name="my_tool")
def tool_call(query: str) -> str:
    """Example tool"""
    ctx = _extract_trace_context()
    token = context.attach(ctx)
    try:
        with tracer.start_as_current_span(
                "my_tool.tool_call",
                kind=SpanKind.SERVER,
                attributes={"my_tool.query": query, "http.route": "/my_tool"},
            ) as span:
            return "hello world"
    finally:
        context.detach(token)

```
