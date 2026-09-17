"""Demonstration locale sur le catalogue d'exemple, sans reseau."""
from jev_mcp_router import DEFAULT_TOOLS, McpSelector

result = McpSelector(provider="local").select(
    query="Lire un fichier local puis chercher des issues GitHub",
    tools=DEFAULT_TOOLS,
    max_tools=2,
    budget_tokens=250,
    min_relevance=0.0,
    scope="demo",
)
print(result.decision, [item.id for item in result.selected], result.total_tokens)
if result.selected:
    print(result.selected[0].reasons)
    print("max_calls", result.selected[0].max_calls)
if result.fallback:
    print("repli", result.fallback.id)
for item in result.rejected:
    print("rejet", item.id, item.reason)
assert result.decision == "select"
assert {item.id for item in result.selected} >= {"filesystem_read", "github_search"}
assert result.selected[0].max_calls >= 1
