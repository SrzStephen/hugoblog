from a2a.types import AgentCard, AgentCapabilities, AgentSkill

from util.settings import mysettings

duck_agent_card = AgentCard(
    name="DuckDuckGo Agent",
    description="An agent that answers questions using a web search, always providing citations.",
    version="1.0.0",
    url=f"{mysettings.server.A2A_BASE_URL}/duckduckgo",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(
        streaming=True,
        push_notifications=False,
        state_transition_history=True,
    ),
    skills=[
        AgentSkill(
            id="duckduckgo-search",
            name="DuckDuckGo Search",
            description="Searches DuckDuckgo to answer questions with citations",
            tags=["duckduckgo", "search", "knowledge"],
        )
    ],
)
