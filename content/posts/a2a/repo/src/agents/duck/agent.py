from functools import cache

from langchain_community.tools import DuckDuckGoSearchResults
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from loguru import logger

from util.config import model

tools = [DuckDuckGoSearchResults()]


@cache
def get_agent() -> CompiledStateGraph:
    _agent = create_agent(
        model,
        tools,
        system_prompt="You are a helpful assistant that always provides citations for what you say",
    )
    logger.info("DuckDuckGo agent created")
    return _agent
