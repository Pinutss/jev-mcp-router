"""Endpoint compatible fourni par l'utilisateur."""
from __future__ import annotations

from ..errors import ConfigurationError
from ..models import SelectRequest, SelectResult, ToolProfile
from ..selector import HeuristicSelector
from .http import post_json
from .scores import parse_score_list


class CustomProvider:
    def __init__(
        self,
        base_url: str,
        api_key: str | None = None,
        timeout: float = 30.0,
        selector: HeuristicSelector | None = None,
    ) -> None:
        if not base_url:
            raise ConfigurationError("JEV_BASE_URL est obligatoire pour le provider custom")
        self._base_url = base_url
        self._api_key = api_key
        self._timeout = timeout
        self._selector = selector or HeuristicSelector()

    def select(self, tools: list[ToolProfile], request: SelectRequest) -> SelectResult:
        payload = {
            "query": request.query,
            "tools": [
                {
                    "id": tool.id,
                    "name": tool.name,
                    "description": tool.description,
                    "server": tool.server,
                    "tags": list(tool.tags),
                }
                for tool in tools
            ],
        }
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        raw = post_json(self._base_url, payload, headers, timeout=self._timeout)
        scores = parse_score_list(raw)
        return self._selector.select(tools, request, jev_scores=scores)
