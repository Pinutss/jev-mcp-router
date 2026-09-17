"""Provider de demonstration, deterministe, hors reseau."""
from __future__ import annotations

from ..models import SelectRequest, SelectResult, ToolProfile
from ..selector import HeuristicSelector


class MockProvider:
    """Classement lexical fixe, pour `jev-mcp demo` et la CI."""

    def __init__(self) -> None:
        self._selector = HeuristicSelector(min_relevance=0.0)

    def select(self, tools: list[ToolProfile], request: SelectRequest) -> SelectResult:
        return self._selector.select(tools, request)
