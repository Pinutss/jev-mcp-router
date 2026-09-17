"""Provider local : heuristique deterministe, hors reseau."""
from __future__ import annotations

from ..models import SelectRequest, SelectResult, ToolProfile
from ..selector import HeuristicSelector


class LocalProvider:
    def __init__(self, selector: HeuristicSelector | None = None) -> None:
        self._selector = selector or HeuristicSelector()

    def select(self, tools: list[ToolProfile], request: SelectRequest) -> SelectResult:
        return self._selector.select(tools, request)
