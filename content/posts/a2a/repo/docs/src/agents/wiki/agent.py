from functools import cache

from langchain_community.tools import WikipediaQueryRun
from langchain_community.utilities import WikipediaAPIWrapper
from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from loguru import logger
from datetime import datetime
from util.config import model

tools = [
    WikipediaQueryRun(
        api_wrapper=WikipediaAPIWrapper(doc_content_chars_max=10000, top_k_results=3)
    )
]


@cache
def get_agent() -> CompiledStateGraph:
    _agent = create_agent(
        model,
        tools,
        system_prompt=f"You are a helpful assistant that always provides citations for what you say"
        f"Today's date is {datetime.now().date()}",
    )
    logger.info("Wikipedia agent created")
    return _agent
