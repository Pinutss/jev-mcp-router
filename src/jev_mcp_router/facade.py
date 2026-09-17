"""Facade publique McpSelector."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from typing import Any

from .catalog import resolve_gateway
from .config import Settings
from .errors import ConfigurationError
from .models import RejectedTool, SelectRequest, SelectResult, ToolProfile
from .providers.custom import CustomProvider
from .providers.gateway import GatewayClient
from .providers.jev import JevClient
from .providers.local import LocalProvider
from .providers.mock import MockProvider
from .security.redaction import redact_text, redact_tool
from .selector import HeuristicSelector


class McpSelector:
    """Point d'entree unique : local, mock, custom ou jev+gateway."""

    def __init__(
        self,
        provider: str | None = None,
        *,
        api_key: str | None = None,
        jev_base_url: str | None = None,
        gateway_api_key: str | None = None,
        gateway_base_url: str | None = None,
        gateway_model: str | None = None,
        settings: Settings | None = None,
        gateway_provider: str | None = None,
        llm_prefer: str | None = None,
    ) -> None:
        env = settings or Settings.from_env()
        requested = (provider if provider is not None else env.provider or "auto").strip().lower()
        use_env_defaults = settings is not None
        self.provider_name = requested
        self.settings = Settings(
            provider=requested,
            jev_api_key=_coalesce(api_key, env.jev_api_key),
            jev_base_url=_coalesce(jev_base_url, env.jev_base_url),
            jev_model=env.jev_model,
            gateway_base_url=_coalesce(gateway_base_url, env.gateway_base_url),
            gateway_api_key=_coalesce(gateway_api_key, env.gateway_api_key),
            gateway_model=_coalesce(gateway_model, env.gateway_model),
            min_relevance=env.min_relevance,
            max_tools=env.max_tools,
            budget_tokens=env.budget_tokens,
            max_candidates=env.max_candidates,
            redact_secrets=env.redact_secrets,
            host=env.host,
            port=env.port,
            auth_token=env.auth_token,
            w_jev=env.w_jev,
            w_gateway=env.w_gateway,
            w_relevance=env.w_relevance,
            w_tokens=env.w_tokens,
            request_timeout=env.request_timeout,
            llm_prefer=_coalesce(llm_prefer, env.llm_prefer),
        )
        self._gateway_provider = gateway_provider
        if requested in {"", "auto"}:
            name = "jev" if self._probe_jev(gateway_provider, llm_prefer) else "local"
        else:
            name = requested
            if name == "jev":
                self._apply_catalog(
                    gateway_provider=gateway_provider, llm_prefer=llm_prefer
                )
        if not use_env_defaults:
            self.settings = replace(
                self.settings,
                min_relevance=env.min_relevance if name == "jev" else 0.0,
                redact_secrets=name in {"jev", "custom"},
            )
        self.provider_name = name
        self.settings = replace(self.settings, provider=name)
        self._validate()

    def _gateway_ready(self) -> bool:
        ollama = (self.settings.gateway_base_url or "").rstrip("/").endswith("11434/v1")
        return bool(
            self.settings.gateway_base_url
            and self.settings.gateway_model
            and (self.settings.gateway_api_key or ollama)
        )

    def _probe_jev(
        self,
        gateway_provider: str | None = None,
        llm_prefer: str | None = None,
    ) -> bool:
        if not (self.settings.jev_api_key and self.settings.jev_base_url):
            return False
        if self._gateway_ready():
            return True
        try:
            self._apply_catalog(gateway_provider=gateway_provider, llm_prefer=llm_prefer)
        except ConfigurationError:
            return False
        return self._gateway_ready()

    def _apply_catalog(
        self,
        gateway_provider: str | None = None,
        gateway_model: str | None = None,
        llm_prefer: str | None = None,
    ) -> None:
        if self.provider_name not in {"jev", "auto", ""}:
            return
        settings = self.settings
        incomplete = not (
            settings.gateway_base_url and settings.gateway_model and settings.gateway_api_key
        )
        explicit = bool(
            gateway_provider
            or gateway_model
            or (llm_prefer and llm_prefer != "named")
        )
        if not incomplete and not explicit:
            return
        endpoint = resolve_gateway(
            provider=gateway_provider or self._gateway_provider,
            model=gateway_model,
            prefer=llm_prefer if llm_prefer and llm_prefer != "named" else None,
        )
        self.settings = replace(
            settings,
            gateway_base_url=settings.gateway_base_url or endpoint.base_url,
            gateway_api_key=settings.gateway_api_key or endpoint.api_key,
            gateway_model=settings.gateway_model or endpoint.model,
        )

    def _validate(self) -> None:
        if self.provider_name not in {"local", "mock", "custom", "jev"}:
            raise ConfigurationError(f"provider inconnu : {self.provider_name}")
        if self.provider_name == "jev":
            missing = [
                name
                for name, value in (
                    ("JEV_API_KEY", self.settings.jev_api_key),
                    ("JEV_BASE_URL", self.settings.jev_base_url),
                    ("GATEWAY_API_KEY", self.settings.gateway_api_key),
                    ("GATEWAY_BASE_URL", self.settings.gateway_base_url),
                    ("GATEWAY_MODEL", self.settings.gateway_model),
                )
                if not value
            ]
            ollama = (self.settings.gateway_base_url or "").rstrip("/").endswith("11434/v1")
            if ollama:
                missing = [name for name in missing if name != "GATEWAY_API_KEY"]
            if missing:
                raise ConfigurationError("provider jev exige " + ", ".join(missing))
        if self.provider_name == "custom" and not self.settings.jev_base_url:
            raise ConfigurationError("JEV_BASE_URL est obligatoire pour le provider custom")

    def select(
        self,
        query: str,
        tools: Sequence[ToolProfile | Mapping[str, Any]],
        *,
        required_permissions: Sequence[str] = (),
        forbidden_permissions: Sequence[str] = (),
        max_tools: int | None = None,
        budget_tokens: int | None = None,
        min_relevance: float | None = None,
        failed_tool_id: str | None = None,
        allow_fallback: bool = True,
        scope: str = "default",
        gateway_provider: str | None = None,
        gateway_model: str | None = None,
        llm_prefer: str | None = None,
    ) -> SelectResult:
        if gateway_provider or gateway_model or llm_prefer:
            self._apply_catalog(
                gateway_provider=gateway_provider,
                gateway_model=gateway_model,
                llm_prefer=llm_prefer,
            )
            self._validate()
        profiles = [ToolProfile.from_mapping(tool) for tool in tools]
        clean_query = redact_text(query) if self.settings.redact_secrets else query
        if self.settings.redact_secrets:
            profiles = [redact_tool(tool) for tool in profiles]
        request = SelectRequest(
            query=clean_query,
            required_permissions=tuple(required_permissions),
            forbidden_permissions=tuple(forbidden_permissions),
            max_tools=self.settings.max_tools if max_tools is None else max_tools,
            budget_tokens=self.settings.budget_tokens if budget_tokens is None else budget_tokens,
            min_relevance=(
                self.settings.min_relevance if min_relevance is None else min_relevance
            ),
            failed_tool_id=failed_tool_id,
            allow_fallback=allow_fallback,
            scope=scope,
        )
        if self.provider_name == "jev":
            return self._select_jev(profiles, request)
        if self.provider_name == "custom":
            return CustomProvider(
                base_url=self.settings.jev_base_url or "",
                api_key=self.settings.jev_api_key,
                timeout=self.settings.request_timeout,
                selector=self._local_selector(),
            ).select(profiles, request)
        if self.provider_name == "mock":
            return MockProvider().select(profiles, request)
        return LocalProvider(self._local_selector()).select(profiles, request)

    def _local_selector(self) -> HeuristicSelector:
        return HeuristicSelector(min_relevance=self.settings.min_relevance)

    def _hybrid_selector(self) -> HeuristicSelector:
        settings = self.settings
        return HeuristicSelector(
            w_relevance=0.0,
            w_tokens=settings.w_tokens,
            w_jev=settings.w_jev,
            w_gateway=settings.w_gateway,
            min_relevance=settings.min_relevance,
        )

    def _select_jev(self, tools: list[ToolProfile], request: SelectRequest) -> SelectResult:
        prefilter = HeuristicSelector(min_relevance=0.0)
        candidates, rejected, _by_id = prefilter.collect(tools, request)
        limited = candidates[: self.settings.max_candidates]
        extra = [
            RejectedTool(tool.id, "max_candidates")
            for _score, _rel, _eff, tool in candidates[self.settings.max_candidates :]
        ]
        top = [tool for _score, _rel, _eff, tool in limited]
        if not top:
            return SelectResult(
                decision="abstain",
                selected=(),
                rejected=tuple(rejected) + tuple(extra),
                reasons=("no_candidate",),
                abstain_reason="no_candidate",
            )

        jev = JevClient(
            api_key=self.settings.jev_api_key or "",
            base_url=self.settings.jev_base_url or "",
            model=self.settings.jev_model,
            timeout=self.settings.request_timeout,
        )
        ollama = (self.settings.gateway_base_url or "").rstrip("/").endswith("11434/v1")
        gateway = GatewayClient(
            api_key=self.settings.gateway_api_key or "",
            base_url=self.settings.gateway_base_url or "",
            model=self.settings.gateway_model or "",
            timeout=self.settings.request_timeout,
            optional_key=ollama,
        )
        with ThreadPoolExecutor(max_workers=2) as pool:
            jev_future = pool.submit(jev.score, request.query, top)
            gw_future = pool.submit(gateway.score, request.query, top)
            jev_scores = jev_future.result()
            gateway_scores = gw_future.result()

        result = self._hybrid_selector().select(
            top, request, jev_scores=jev_scores, gateway_scores=gateway_scores
        )
        return SelectResult(
            decision=result.decision,
            selected=result.selected,
            fallback=result.fallback,
            rejected=tuple(rejected) + tuple(extra) + result.rejected,
            total_tokens=result.total_tokens,
            reasons=result.reasons,
            abstain_reason=result.abstain_reason,
        )


def _coalesce(explicit: str | None, fallback: str | None) -> str | None:
    return explicit if explicit is not None else fallback
