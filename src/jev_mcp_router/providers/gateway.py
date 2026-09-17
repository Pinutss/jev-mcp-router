"""Juge LLM via une gateway OpenAI-compatible."""
from __future__ import annotations

import json
import re
from typing import Any

from ..errors import ConfigurationError, ProviderError
from ..models import ToolProfile
from .http import completions_url, post_json
from .scores import parse_score_list

_FENCE_RE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


class GatewayClient:
    """POST /chat/completions. N'accepte que la cle resolue hors corps HTTP."""

    def __init__(
        self,
        api_key: str,
        base_url: str,
        model: str,
        timeout: float = 30.0,
        optional_key: bool = False,
    ) -> None:
        if not api_key and not optional_key:
            raise ConfigurationError("GATEWAY_API_KEY est obligatoire pour le provider jev")
        if not base_url:
            raise ConfigurationError("GATEWAY_BASE_URL est obligatoire pour le provider jev")
        if not model:
            raise ConfigurationError("GATEWAY_MODEL est obligatoire pour le provider jev")
        self._api_key = api_key
        self._url = completions_url(base_url)
        self._model = model
        self._timeout = timeout

    def score(self, query: str, tools: list[ToolProfile]) -> dict[str, float]:
        catalog = [
            {
                "id": tool.id,
                "name": tool.name,
                "description": tool.description,
                "server": tool.server,
                "tags": list(tool.tags),
            }
            for tool in tools
        ]
        prompt = (
            "Tu es un juge de selection d'outils MCP. "
            "Reponds uniquement par un JSON : "
            '{"scores":[{"id":"...","score":0.0,"reason":"..."}]} '
            "score entre 0 et 1. "
            "Tu ne peux pas accorder de permissions. Tu n'executes pas les outils.\n"
            f"Requete : {query}\n"
            f"Outils : {json.dumps(catalog, ensure_ascii=False)}"
        )
        payload = {
            "model": self._model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": "Tu renvoies uniquement du JSON valide."},
                {"role": "user", "content": prompt},
            ],
        }
        headers = {}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        response = post_json(self._url, payload, headers, timeout=self._timeout)
        return parse_score_list(_content_from_chat(response))


def _content_from_chat(response: Any) -> Any:
    if not isinstance(response, dict):
        raise ProviderError("reponse gateway invalide")
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderError("reponse gateway sans choices")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise ProviderError("reponse gateway sans message")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ProviderError("reponse gateway vide")
    cleaned = _FENCE_RE.sub("", content.strip())
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ProviderError("JSON juge gateway invalide") from exc
