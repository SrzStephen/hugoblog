from a2a.types import AgentCard, AgentCapabilities, AgentSkill

from util.settings import mysettings

wikipedia_agent_card = AgentCard(
    name="Wikipedia Agent",
    description="An agent that answers questions using Wikipedia, always providing citations.",
    url=f"{mysettings.server.A2A_BASE_URL}/wikipedia",
    version="1.0.0",
    default_input_modes=["text/plain"],
    default_output_modes=["text/plain"],
    capabilities=AgentCapabilities(
        streaming=True,
        push_notifications=False,
        state_transition_history=True,
    ),
    skills=[
        AgentSkill(
            id="wikipedia-search",
            name="Wikipedia Search",
            description="Searches Wikipedia to answer questions with citations",
            tags=["wikipedia", "search", "knowledge"],
        )
    ],
)
