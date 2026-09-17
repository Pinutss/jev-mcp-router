"""Modeles de donnees du selecteur d'outils MCP."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Literal

Decision = Literal["select", "fallback", "abstain"]


def _as_tuple(value: object) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
        return tuple(part for part in parts if part)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise ValueError("attendu une liste ou une chaine")


def _as_bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return bool(value)


def normalize_token(value: str) -> str:
    """Normalise une permission pour les comparaisons."""
    return value.strip().lower()


@dataclass(frozen=True)
class ToolProfile:
    """Un outil declare dans le catalogue.

    permissions et max_calls viennent uniquement du catalogue. Ni la
    requete, ni un outil, ni un modele ne peuvent les augmenter.
    """

    id: str
    name: str
    description: str = ""
    server: str = ""
    tags: tuple[str, ...] = ()
    tokens: int = 80
    permissions: tuple[str, ...] = ()
    enabled: bool = True
    fallback_id: str | None = None
    max_calls: int = 8
    scope: str = "default"

    def __post_init__(self) -> None:
        if not self.id:
            raise ValueError("id est obligatoire")
        if not self.name:
            raise ValueError("name est obligatoire")
        if self.tokens < 1:
            raise ValueError("tokens doit etre >= 1")
        if self.max_calls < 1:
            raise ValueError("max_calls doit etre >= 1")

    @property
    def permission_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.permissions)

    def with_description(self, description: str) -> ToolProfile:
        return ToolProfile(
            id=self.id,
            name=self.name,
            description=description,
            server=self.server,
            tags=self.tags,
            tokens=self.tokens,
            permissions=self.permissions,
            enabled=self.enabled,
            fallback_id=self.fallback_id,
            max_calls=self.max_calls,
            scope=self.scope,
        )

    @classmethod
    def from_mapping(cls, data: ToolProfile | Mapping[str, Any]) -> ToolProfile:
        if isinstance(data, cls):
            return data
        fallback = data.get("fallback_id") or data.get("fallback")
        return cls(
            id=str(data.get("id") or ""),
            name=str(data.get("name") or data.get("id") or ""),
            description=str(data.get("description") or ""),
            server=str(data.get("server") or ""),
            tags=_as_tuple(data.get("tags")),
            tokens=int(data.get("tokens", 80)),
            permissions=_as_tuple(data.get("permissions")),
            enabled=_as_bool(data.get("enabled"), True),
            fallback_id=None if not fallback else str(fallback),
            max_calls=int(data.get("max_calls", 8)),
            scope=str(data.get("scope") or data.get("namespace") or "default"),
        )


@dataclass(frozen=True)
class SelectRequest:
    """Une demande de selection.

    required_permissions et forbidden_permissions sont declares par
    l'appelant, jamais extraits de la requete ou d'un outil.
    """

    query: str
    required_permissions: tuple[str, ...] = ()
    forbidden_permissions: tuple[str, ...] = ()
    max_tools: int = 8
    budget_tokens: int = 800
    min_relevance: float = 0.15
    failed_tool_id: str | None = None
    allow_fallback: bool = True
    scope: str = "default"

    def __post_init__(self) -> None:
        if not self.query.strip():
            raise ValueError("query est obligatoire")
        if self.max_tools < 1:
            raise ValueError("max_tools doit etre >= 1")
        if self.budget_tokens < 1:
            raise ValueError("budget_tokens doit etre >= 1")
        if not 0.0 <= self.min_relevance <= 1.0:
            raise ValueError("min_relevance doit etre compris entre 0.0 et 1.0")

    @property
    def required_permission_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.required_permissions)

    @property
    def forbidden_permission_set(self) -> frozenset[str]:
        return frozenset(normalize_token(item) for item in self.forbidden_permissions)

    @classmethod
    def from_mapping(
        cls, data: Mapping[str, Any], defaults: SelectRequest | None = None
    ) -> SelectRequest:
        base = defaults
        failed = data.get("failed_tool_id")
        return cls(
            query=str(data.get("query") or (base.query if base else "")),
            required_permissions=_as_tuple(
                data.get("required_permissions", base.required_permissions if base else ())
            ),
            forbidden_permissions=_as_tuple(
                data.get("forbidden_permissions", base.forbidden_permissions if base else ())
            ),
            max_tools=int(data.get("max_tools", base.max_tools if base else 8)),
            budget_tokens=int(data.get("budget_tokens", base.budget_tokens if base else 800)),
            min_relevance=float(
                data.get("min_relevance", base.min_relevance if base else 0.15)
            ),
            failed_tool_id=None if failed in (None, "") else str(failed),
            allow_fallback=_as_bool(
                data.get("allow_fallback"), base.allow_fallback if base else True
            ),
            scope=str(data.get("scope") or (base.scope if base else "default")),
        )


@dataclass(frozen=True)
class SelectedTool:
    """Un outil retenu, avec score et justification."""

    id: str
    name: str
    server: str
    score: float
    tokens: int
    reasons: tuple[str, ...]
    permissions: tuple[str, ...]
    max_calls: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "server": self.server,
            "score": self.score,
            "tokens": self.tokens,
            "reasons": list(self.reasons),
            "permissions": list(self.permissions),
            "max_calls": self.max_calls,
        }


@dataclass(frozen=True)
class RejectedTool:
    """Un outil ecarte, avec la cause du rejet."""

    id: str
    reason: str


@dataclass(frozen=True)
class SelectResult:
    """Le resultat d'une selection."""

    decision: Decision
    selected: tuple[SelectedTool, ...]
    fallback: SelectedTool | None = None
    rejected: tuple[RejectedTool, ...] = ()
    total_tokens: int = 0
    reasons: tuple[str, ...] = ()
    abstain_reason: str | None = None

    def to_dict(self, *, include_rejected: bool = True) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "decision": self.decision,
            "selected": [item.to_dict() for item in self.selected],
            "fallback": None if self.fallback is None else self.fallback.to_dict(),
            "total_tokens": self.total_tokens,
            "reasons": list(self.reasons),
            "abstain_reason": self.abstain_reason,
        }
        if include_rejected:
            payload["rejected"] = [
                {"id": item.id, "reason": item.reason} for item in self.rejected
            ]
        return payload
