from urllib.parse import urlparse

from a2a.types import AgentCard


def get_route(card: AgentCard) -> str:
    """Extract the route path from an agent card's URL (e.g. '/wikipedia')."""
    return urlparse(card.url).path
