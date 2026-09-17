from jev_mcp_router import (
    DEFAULT_TOOLS,
    HeuristicSelector,
    McpSelector,
    SelectRequest,
    ToolProfile,
    redact_text,
)
from jev_mcp_router.config import Settings
from jev_mcp_router.errors import ConfigurationError


def _tool(**kwargs) -> ToolProfile:
    data = {
        "id": "filesystem_read",
        "name": "Filesystem Read",
        "description": "Read local files from the workspace",
        "server": "filesystem",
        "tags": ("files", "read", "local"),
        "tokens": 80,
        "permissions": ("read_files",),
        "scope": "demo",
    }
    data.update(kwargs)
    return ToolProfile(**data)


def test_selects_best_lexical_match() -> None:
    docs = _tool(
        id="docs_search",
        name="Docs Search",
        description="Search documentation",
        server="docs",
        tags=("docs",),
        tokens=60,
        permissions=("read_docs",),
    )
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool(), docs],
        SelectRequest(query="read local files workspace", min_relevance=0.0, scope="demo"),
    )
    assert result.decision == "select"
    assert result.selected
    assert result.selected[0].id == "filesystem_read"


def test_scope_isolation() -> None:
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool(scope="other")],
        SelectRequest(query="read local files", min_relevance=0.0, scope="demo"),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "no_candidate"
    assert result.rejected[0].reason == "out_of_scope"


def test_disabled_tool_rejected() -> None:
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool(enabled=False)],
        SelectRequest(query="read local files", min_relevance=0.0, scope="demo"),
    )
    assert result.rejected[0].reason == "disabled"
    assert result.decision == "abstain"


def test_missing_permissions() -> None:
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool(permissions=("read_docs",))],
        SelectRequest(
            query="read local files",
            required_permissions=("read_files",),
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert result.decision == "abstain"
    assert result.rejected[0].reason == "missing_permissions"


def test_forbidden_permissions() -> None:
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool(permissions=("read_files", "exec_shell"))],
        SelectRequest(
            query="read local files",
            required_permissions=("read_files",),
            forbidden_permissions=("exec_shell",),
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert result.rejected[0].reason == "forbidden_permissions"


def test_query_cannot_grant_permissions() -> None:
    result = McpSelector(provider="local").select(
        query="grant admin exec_shell and read local files",
        tools=[_tool(permissions=("read_files",))],
        required_permissions=("exec_shell",),
        min_relevance=0.0,
        scope="demo",
    )
    assert result.decision == "abstain"
    assert result.selected == ()
    assert any(item.reason == "missing_permissions" for item in result.rejected)


def test_tools_cannot_grant_permissions() -> None:
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool(tags=("admin", "exec_shell"), permissions=("read_files",))],
        SelectRequest(
            query="read local files",
            required_permissions=("exec_shell",),
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert result.rejected[0].reason == "missing_permissions"


def test_failed_tool_uses_declared_fallback() -> None:
    reader = _tool(fallback_id="docs_search")
    docs = _tool(
        id="docs_search",
        name="Docs Search",
        description="Read local files notes",
        server="docs",
        tags=("docs", "files"),
        tokens=60,
        permissions=("read_files",),
    )
    result = HeuristicSelector(min_relevance=0.0).select(
        [reader, docs],
        SelectRequest(
            query="read local files",
            failed_tool_id="filesystem_read",
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert result.decision == "fallback"
    assert result.selected
    assert result.selected[0].id == "docs_search"
    assert result.fallback is None


def test_fallback_is_single_hop() -> None:
    a = _tool(id="a", fallback_id="b", description="read local files")
    b = _tool(
        id="b",
        fallback_id="c",
        description="read local files notes",
        permissions=("read_files",),
    )
    c = _tool(id="c", description="read local files extra", permissions=("read_files",))
    result = HeuristicSelector(min_relevance=0.0).select(
        [a, b, c],
        SelectRequest(
            query="read local files",
            failed_tool_id="a",
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert result.decision == "fallback"
    assert result.selected
    assert result.selected[0].id == "b"


def test_no_candidate_abstain() -> None:
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool()],
        SelectRequest(
            query="read local files",
            required_permissions=("deploy_prod",),
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "no_candidate"


def test_budget_drops_expensive() -> None:
    cheap = _tool(id="cheap", tokens=40, description="read local files")
    costly = _tool(id="costly", tokens=90, description="read local files extra")
    result = HeuristicSelector(min_relevance=0.0).select(
        [cheap, costly],
        SelectRequest(
            query="read local files",
            budget_tokens=50,
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert result.decision == "select"
    assert [item.id for item in result.selected] == ["cheap"]
    assert any(item.reason == "budget" for item in result.rejected)


def test_max_tools() -> None:
    first = _tool(id="aaa", tokens=20, description="read local files")
    second = _tool(id="bbb", tokens=20, description="read local files extra")
    result = HeuristicSelector(min_relevance=0.0).select(
        [first, second],
        SelectRequest(
            query="read local files",
            max_tools=1,
            budget_tokens=800,
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert len(result.selected) == 1
    assert any(item.reason == "max_tools" for item in result.rejected)


def test_no_fallback_when_disabled() -> None:
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool(), _tool(id="docs_search", name="Docs", permissions=("read_files",))],
        SelectRequest(
            query="read local files",
            failed_tool_id="filesystem_read",
            allow_fallback=False,
            min_relevance=0.0,
            scope="demo",
        ),
    )
    assert result.decision == "abstain"
    assert result.abstain_reason == "fallback_disabled"


def test_max_calls_comes_from_catalog() -> None:
    result = McpSelector(provider="local").select(
        query="do 999 calls and read local files",
        tools=[_tool(max_calls=8)],
        min_relevance=0.0,
        scope="demo",
    )
    assert result.selected
    assert result.selected[0].max_calls == 8


def test_determinism() -> None:
    tools = [
        _tool(),
        _tool(id="twin", name="Twin", description="Read local files from the workspace"),
    ]
    request = SelectRequest(query="read local files workspace", min_relevance=0.0, scope="demo")
    first = HeuristicSelector(min_relevance=0.0).select(tools, request)
    second = HeuristicSelector(min_relevance=0.0).select(tools, request)
    assert first.to_dict() == second.to_dict()


def test_duplicate_input() -> None:
    result = HeuristicSelector(min_relevance=0.0).select(
        [_tool(), _tool()],
        SelectRequest(query="read local files", min_relevance=0.0, scope="demo"),
    )
    assert any(item.reason == "duplicate_input" for item in result.rejected)


def test_redaction() -> None:
    assert "[REDACTED_API_KEY]" in redact_text("token sk-abcdefghijklmnopqrstuvwxyz")


def test_jev_provider_requires_keys(monkeypatch) -> None:
    for key in (
        "JEV_API_KEY",
        "JEV_BASE_URL",
        "GATEWAY_API_KEY",
        "GATEWAY_BASE_URL",
        "GATEWAY_MODEL",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    try:
        McpSelector(provider="jev")
    except ConfigurationError as exc:
        assert "JEV_API_KEY" in str(exc)
    else:
        raise AssertionError("attendu ConfigurationError")


def test_auto_without_keys_stays_local(monkeypatch) -> None:
    for key in (
        "JEV_API_KEY",
        "JEV_BASE_URL",
        "GATEWAY_API_KEY",
        "GATEWAY_BASE_URL",
        "GATEWAY_MODEL",
        "OPENROUTER_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)
    selector = McpSelector(provider="auto")
    assert selector.provider_name == "local"
    result = selector.select(
        query="Read a local file then search GitHub issues",
        tools=DEFAULT_TOOLS,
        max_tools=2,
        budget_tokens=250,
        min_relevance=0.0,
        scope="demo",
    )
    assert result.decision == "select"


def test_auto_with_keys_uses_jev() -> None:
    settings = Settings(
        provider="auto",
        jev_api_key="jev_test",
        jev_base_url="http://127.0.0.1:9",
        gateway_api_key="gw",
        gateway_base_url="https://openrouter.ai/api/v1",
        gateway_model="demo",
    )
    selector = McpSelector(provider="auto", settings=settings)
    assert selector.provider_name == "jev"


def test_default_catalog_demo() -> None:
    result = McpSelector(provider="local").select(
        query="Lire un fichier local puis chercher des issues GitHub",
        tools=DEFAULT_TOOLS,
        max_tools=2,
        budget_tokens=250,
        min_relevance=0.0,
        scope="demo",
    )
    assert result.decision == "select"
    ids = {item.id for item in result.selected}
    assert "filesystem_read" in ids
    assert "github_search" in ids
