from langchain.agents import create_agent
from langgraph.graph.state import CompiledStateGraph
from langchain_core.tools import BaseTool, tool
from loguru import logger
from pandas import DataFrame

from util.config import model

# Expectations:
# Admin: Only members of data_fetch_admin.caller should be able to call rows related to admin
# User: Only authenticated users
# Guest: Any user

example_frame = DataFrame(
    {
        "row_access": ["admin", "user", "guest", "admin", "user"],
        "value": [100, 200, 300, 400, 500],
    }
)


def make_data_fetch_tool(is_authenticated: bool, user_roles: list[str]) -> BaseTool:
    """Create a data fetch tool with row-level access control."""

    allowed = ["guest"]
    if is_authenticated:
        allowed.append("user")
    if "data_fetch_admin.caller" in user_roles:
        allowed.append("admin")

    @tool
    def fetch_data() -> str:
        """Fetch data from the dataset. Returns rows the current user is allowed to see based on their access level."""
        filtered = example_frame[example_frame["row_access"].isin(allowed)]
        return filtered.to_string(index=False)

    return fetch_data


def get_text_agent(is_authenticated: bool, user_roles: list[str]) -> CompiledStateGraph:
    """Create a per-request LangChain agent with row-level access control."""
    data_tool = make_data_fetch_tool(is_authenticated, user_roles)
    agent = create_agent(
        model,
        [data_tool],
        system_prompt="You are a data assistant. Use the fetch_data tool to retrieve data for the user.",
    )
    logger.info(
        "Text agent created — authenticated={}, roles={}",
        is_authenticated,
        user_roles,
    )
    return agent
