"""Interface commune des providers."""
from __future__ import annotations

from typing import Protocol

from ..models import SelectRequest, SelectResult, ToolProfile


class DecisionProvider(Protocol):
    def select(
        self,
        tools: list[ToolProfile],
        request: SelectRequest,
    ) -> SelectResult:
        """Retourne une decision de selection."""
        ...
