"""Selecteur heuristique deterministe, sans dependance a l'execution."""
from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .models import (
    RejectedTool,
    SelectedTool,
    SelectRequest,
    SelectResult,
    ToolProfile,
)

_WORD_RE = re.compile(r"[a-z0-9àâäéèêëíìîïòóôöùúûüçñ]+")
_STOPWORDS = frozenset(
    """au aux avec ce ces dans de des du elle en et eux il je la le les leur lui ma
    mais me meme mes moi mon ne nos notre nous on ou par pas pour qu que qui sa se
    ses son sur ta te tes toi ton tu un une vos votre vous c d j l à m n s t y été
    the a an and or of to in for with without is are was were be been this that
    """.split()
)

Candidate = tuple[float, float, float, ToolProfile]


def tokenize(text: str) -> frozenset[str]:
    """Jetons minuscules, sans mots vides, pour le scoring lexical."""
    return frozenset(
        word
        for word in _WORD_RE.findall(text.lower())
        if (len(word) > 1 or word.isdigit()) and word not in _STOPWORDS
    )


def tool_tokens(tool: ToolProfile) -> frozenset[str]:
    tokens = set(tokenize(f"{tool.name} {tool.description} {tool.server}"))
    for tag in tool.tags:
        tokens.update(tokenize(tag))
        tokens.add(tag.strip().lower())
    return frozenset(tokens)


def token_efficiency(tokens: int) -> float:
    """Inversion legere du cout en jetons (outils plus petits legerement privilegies)."""
    return 1.0 / (1.0 + tokens / 100.0)


def _hard_reject(tool: ToolProfile, request: SelectRequest) -> str | None:
    if tool.scope != request.scope:
        return "out_of_scope"
    if not tool.enabled:
        return "disabled"
    if request.failed_tool_id and tool.id == request.failed_tool_id:
        return "already_failed"
    required = request.required_permission_set
    if required and not required <= tool.permission_set:
        return "missing_permissions"
    if request.forbidden_permission_set & tool.permission_set:
        return "forbidden_permissions"
    return None


@dataclass
class HeuristicSelector:
    """Selection deterministe sous budget, avec abstention et repli d'un seul saut.

    Score = pertinence lexicale * w_relevance
          + efficacite jetons (inversion legere) * w_tokens
          + score JEV * w_jev
          + score gateway * w_gateway

    Les politiques d'acces precedent le score. Un juge distant ne peut
    ni reintroduire un outil rejete, ni accorder une permission.
    """

    w_relevance: float = 0.7
    w_tokens: float = 0.3
    w_jev: float = 0.0
    w_gateway: float = 0.0
    min_relevance: float = 0.0

    def __post_init__(self) -> None:
        if not 0.0 <= self.min_relevance <= 1.0:
            raise ValueError("min_relevance doit etre compris entre 0.0 et 1.0")

    def collect(
        self,
        tools: list[ToolProfile],
        request: SelectRequest,
        jev_scores: Mapping[str, float] | None = None,
        gateway_scores: Mapping[str, float] | None = None,
    ) -> tuple[list[Candidate], list[RejectedTool], dict[str, ToolProfile]]:
        jev_scores = jev_scores or {}
        gateway_scores = gateway_scores or {}
        query_tokens = tokenize(request.query)
        rejected: list[RejectedTool] = []
        seen: set[str] = set()
        by_id: dict[str, ToolProfile] = {}
        candidates: list[Candidate] = []
        threshold = max(self.min_relevance, request.min_relevance)

        for tool in tools:
            if tool.id in seen:
                rejected.append(RejectedTool(tool.id, "duplicate_input"))
                continue
            seen.add(tool.id)
            by_id[tool.id] = tool
            reason = _hard_reject(tool, request)
            if reason is not None:
                rejected.append(RejectedTool(tool.id, reason))
                continue

            tokens = tool_tokens(tool)
            relevance = len(query_tokens & tokens) / len(query_tokens) if query_tokens else 0.0
            jev_score = float(jev_scores.get(tool.id, 0.0))
            gateway_score = float(gateway_scores.get(tool.id, 0.0))
            threshold_signal = max(relevance, jev_score, gateway_score)
            if query_tokens and threshold_signal < threshold:
                rejected.append(RejectedTool(tool.id, "low_relevance"))
                continue

            efficiency = token_efficiency(tool.tokens)
            score = (
                self.w_relevance * relevance
                + self.w_tokens * efficiency
                + self.w_jev * jev_score
                + self.w_gateway * gateway_score
            )
            candidates.append((score, relevance, efficiency, tool))

        candidates.sort(key=lambda c: (-round(c[0], 6), c[3].id))
        return candidates, rejected, by_id

    def apply_budget(
        self,
        candidates: list[Candidate],
        request: SelectRequest,
        jev_scores: Mapping[str, float] | None = None,
        gateway_scores: Mapping[str, float] | None = None,
    ) -> tuple[list[SelectedTool], list[RejectedTool], int]:
        jev_scores = jev_scores or {}
        gateway_scores = gateway_scores or {}
        selected: list[SelectedTool] = []
        rejected: list[RejectedTool] = []
        total = 0
        for score, relevance, efficiency, tool in candidates:
            if len(selected) >= request.max_tools:
                rejected.append(RejectedTool(tool.id, "max_tools"))
                continue
            if total + tool.tokens > request.budget_tokens:
                rejected.append(RejectedTool(tool.id, "budget"))
                continue
            selected.append(
                self._to_selected(
                    score, relevance, efficiency, tool, jev_scores, gateway_scores
                )
            )
            total += tool.tokens
        return selected, rejected, total

    def select(
        self,
        tools: list[ToolProfile],
        request: SelectRequest,
        jev_scores: Mapping[str, float] | None = None,
        gateway_scores: Mapping[str, float] | None = None,
    ) -> SelectResult:
        jev_scores = jev_scores or {}
        gateway_scores = gateway_scores or {}
        candidates, rejected, by_id = self.collect(
            tools, request, jev_scores=jev_scores, gateway_scores=gateway_scores
        )
        if request.failed_tool_id:
            return self._after_failure(
                request, candidates, rejected, by_id, jev_scores, gateway_scores
            )

        selected, extra, total = self.apply_budget(
            candidates, request, jev_scores=jev_scores, gateway_scores=gateway_scores
        )
        rejected.extend(extra)
        if not selected:
            return SelectResult(
                decision="abstain",
                selected=(),
                rejected=tuple(rejected),
                total_tokens=0,
                reasons=("no_candidate",),
                abstain_reason="no_candidate",
            )

        fallback = self._fallback_preview(
            selected, candidates, request, jev_scores, gateway_scores
        )
        return SelectResult(
            decision="select",
            selected=tuple(selected),
            fallback=fallback,
            rejected=tuple(rejected),
            total_tokens=total,
            reasons=("best_match",) + selected[0].reasons,
        )

    def _after_failure(
        self,
        request: SelectRequest,
        candidates: list[Candidate],
        rejected: list[RejectedTool],
        by_id: dict[str, ToolProfile],
        jev_scores: Mapping[str, float],
        gateway_scores: Mapping[str, float],
    ) -> SelectResult:
        failed_id = request.failed_tool_id or ""
        if failed_id not in by_id:
            rejected.append(RejectedTool(failed_id, "tool_absent"))
        if not request.allow_fallback:
            return SelectResult(
                decision="abstain",
                selected=(),
                rejected=tuple(rejected),
                reasons=("fallback_disabled",),
                abstain_reason="fallback_disabled",
            )

        preferred_id = None
        failed = by_id.get(failed_id)
        if failed is not None:
            preferred_id = failed.fallback_id

        ordered = list(candidates)
        if preferred_id:
            preferred = [row for row in ordered if row[3].id == preferred_id]
            rest = [row for row in ordered if row[3].id != preferred_id]
            if not preferred:
                rejected.append(RejectedTool(preferred_id, "fallback_unavailable"))
                ordered = rest
            else:
                ordered = preferred + rest

        selected, extra, total = self.apply_budget(
            ordered, request, jev_scores=jev_scores, gateway_scores=gateway_scores
        )
        rejected.extend(extra)
        if not selected:
            return SelectResult(
                decision="abstain",
                selected=(),
                rejected=tuple(rejected),
                total_tokens=0,
                reasons=("no_fallback",),
                abstain_reason="no_fallback",
            )
        return SelectResult(
            decision="fallback",
            selected=tuple(selected),
            fallback=None,
            rejected=tuple(rejected),
            total_tokens=total,
            reasons=(f"failed:{failed_id}", "bounded_fallback") + selected[0].reasons,
        )

    def _fallback_preview(
        self,
        selected: list[SelectedTool],
        candidates: list[Candidate],
        request: SelectRequest,
        jev_scores: Mapping[str, float],
        gateway_scores: Mapping[str, float],
    ) -> SelectedTool | None:
        if not request.allow_fallback or not selected:
            return None
        chosen_ids = {item.id for item in selected}
        top = next((row for row in candidates if row[3].id == selected[0].id), None)
        if top is None or not top[3].fallback_id:
            return None
        preview = next((row for row in candidates if row[3].id == top[3].fallback_id), None)
        if preview is None or preview[3].id in chosen_ids:
            return None
        score, relevance, efficiency, tool = preview
        return self._to_selected(score, relevance, efficiency, tool, jev_scores, gateway_scores)

    def _to_selected(
        self,
        score: float,
        relevance: float,
        efficiency: float,
        tool: ToolProfile,
        jev_scores: Mapping[str, float],
        gateway_scores: Mapping[str, float],
    ) -> SelectedTool:
        reasons = [
            f"relevance={relevance:.2f}",
            f"tokens={tool.tokens}",
            f"efficiency={efficiency:.2f}",
            f"max_calls={tool.max_calls}",
        ]
        if tool.id in jev_scores:
            reasons.append(f"jev={float(jev_scores[tool.id]):.2f}")
        if tool.id in gateway_scores:
            reasons.append(f"gateway={float(gateway_scores[tool.id]):.2f}")
        return SelectedTool(
            id=tool.id,
            name=tool.name,
            server=tool.server,
            score=round(score, 6),
            tokens=tool.tokens,
            reasons=tuple(reasons),
            permissions=tool.permissions,
            max_calls=tool.max_calls,
        )
