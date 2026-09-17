"""Interface en ligne de commande."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .config import Settings, load_dotenv
from .facade import McpSelector
from .mcp_server import run_mcp
from .registry import DEFAULT_TOOLS


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    parser = argparse.ArgumentParser(prog="jev-mcp", description="Selecteur d'outils MCP JEV")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("demo", help="Demonstration locale sans cle ni reseau")
    select = sub.add_parser("select", help="Selection selon JEV_PROVIDER")
    select.add_argument("--file", required=True, help="JSON {query?, tools}")
    select.add_argument("--query", default=None)
    select.add_argument("--scope", default="default")
    sub.add_parser("serve", help="Serveur HTTP /v1/select")
    sub.add_parser("mcp", help="Serveur MCP stdio (mcp_select)")
    bench = sub.add_parser("benchmark", help="Jeu annote local, hors JEV")
    bench.add_argument(
        "--file",
        default=str(Path(__file__).resolve().parents[2] / "benchmarks" / "annotated_tasks.json"),
    )

    args = parser.parse_args(argv)
    if args.command == "demo":
        return _demo()
    if args.command == "select":
        return _select(args.file, args.query, args.scope)
    if args.command == "serve":
        from .api.server import serve

        serve(Settings.from_env())
        return 0
    if args.command == "mcp":
        run_mcp(Settings.from_env())
        return 0
    if args.command == "benchmark":
        return _benchmark(args.file)
    parser.error("commande inconnue")
    return 2


def _demo() -> int:
    selector = McpSelector(provider="mock")
    result = selector.select(
        query="Lire un fichier local puis chercher des issues GitHub",
        tools=DEFAULT_TOOLS,
        max_tools=2,
        budget_tokens=250,
        min_relevance=0.0,
        scope="demo",
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _select(path: str, query: str | None, scope: str) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        print("objet JSON requis", file=sys.stderr)
        return 2
    tools = payload.get("tools")
    chosen_query = query or payload.get("query")
    if not chosen_query:
        print("query manquante (--query ou champ JSON)", file=sys.stderr)
        return 2
    if not isinstance(tools, list):
        print("tools (array) obligatoire", file=sys.stderr)
        return 2
    settings = Settings.from_env()
    result = McpSelector(provider=settings.provider, settings=settings).select(
        query=str(chosen_query),
        tools=tools,
        required_permissions=payload.get("required_permissions") or (),
        forbidden_permissions=payload.get("forbidden_permissions") or (),
        max_tools=payload.get("max_tools"),
        budget_tokens=payload.get("budget_tokens"),
        min_relevance=payload.get("min_relevance"),
        failed_tool_id=payload.get("failed_tool_id"),
        allow_fallback=payload.get("allow_fallback", True),
        scope=str(payload.get("scope") or scope),
        gateway_provider=payload.get("gateway_provider"),
        gateway_model=payload.get("gateway_model"),
        llm_prefer=payload.get("llm_prefer"),
    )
    print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
    return 0


def _benchmark(path: str) -> int:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(cases, list):
        print("cases (array) obligatoire", file=sys.stderr)
        return 2
    selector = McpSelector(provider="local")
    ok = 0
    for case in cases:
        tools = case.get("tools") or DEFAULT_TOOLS
        result = selector.select(
            query=str(case["query"]),
            tools=tools,
            required_permissions=case.get("required_permissions") or (),
            forbidden_permissions=case.get("forbidden_permissions") or (),
            max_tools=case.get("max_tools") or 8,
            budget_tokens=case.get("budget_tokens") or 800,
            min_relevance=case.get("min_relevance", 0.0),
            allow_fallback=case.get("allow_fallback", True),
            failed_tool_id=case.get("failed_tool_id"),
            scope=str(case.get("scope") or "demo"),
        )
        expected_decision = case.get("expected_decision")
        expected_tool = case.get("expected")
        decision_ok = expected_decision is None or result.decision == expected_decision
        tool_ok = expected_tool is None or (
            result.selected and result.selected[0].id == expected_tool
        )
        passed = decision_ok and tool_ok
        ok += int(passed)
        mark = "ok" if passed else "ko"
        chosen = result.selected[0].id if result.selected else result.abstain_reason
        print(f"{mark} {case.get('id', '?')} -> {result.decision}:{chosen}")
    total = len(cases)
    print(f"{ok}/{total} local baseline")
    return 0 if ok == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
