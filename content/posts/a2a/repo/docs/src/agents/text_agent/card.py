from a2a.types import AgentCard, AgentCapabilities, AgentSkill

from util.settings import mysettings

text_agent_card = AgentCard(
    name="Data Agent",
    description="An agent that fetches data with row-level access control based on user authentication and roles.",
    url=f"{mysettings.server.A2A_BASE_URL}/data",
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
            id="data-fetch",
            name="Data Fetch",
            description="Fetches data with row-level security based on user access level",
            tags=["data", "security", "access-control"],
        )
    ],
)
