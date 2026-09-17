import io
import json

from jev_mcp_router.api.server import handle_llms, handle_select
from jev_mcp_router.cli import main
from jev_mcp_router.config import Settings
from jev_mcp_router.mcp_server import _dispatch


def test_handle_select_rejects_keys_in_body() -> None:
    try:
        handle_select(
            {"query": "x", "tools": [], "api_key": "secret"},
            Settings(provider="local"),
            show_rejected=True,
        )
    except Exception as exc:
        assert "cles" in str(exc)
    else:
        raise AssertionError("attendu un refus")


def test_handle_select_rejects_gateway_key() -> None:
    try:
        handle_select(
            {"query": "x", "tools": [], "gateway_api_key": "secret"},
            Settings(provider="local"),
            show_rejected=True,
        )
    except Exception as exc:
        assert "cles" in str(exc)
    else:
        raise AssertionError("attendu un refus")


def test_handle_select_selects() -> None:
    payload = handle_select(
        {
            "query": "read local files workspace",
            "scope": "demo",
            "min_relevance": 0.0,
            "tools": [
                {
                    "id": "filesystem_read",
                    "name": "Filesystem Read",
                    "description": "Read local files from the workspace",
                    "server": "filesystem",
                    "tags": ["files", "read", "local"],
                    "permissions": ["read_files"],
                    "tokens": 80,
                    "scope": "demo",
                }
            ],
        },
        Settings(provider="local"),
        show_rejected=True,
    )
    assert payload["decision"] == "select"
    assert payload["selected"][0]["id"] == "filesystem_read"


def test_handle_llms_is_public() -> None:
    payload = handle_llms()
    assert "llms" in payload
    blob = json.dumps(payload)
    assert "api_key" not in blob.replace("api_key_env", "")
    for row in payload["llms"]:
        assert "api_key" not in row


def test_mcp_lists_tool() -> None:
    response = _dispatch({"id": 1, "method": "tools/list"}, Settings(provider="local"))
    assert response is not None
    tools = response["result"]["tools"]
    assert tools[0]["name"] == "mcp_select"


def test_mcp_selects() -> None:
    response = _dispatch(
        {
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "mcp_select",
                "arguments": {
                    "query": "read local files workspace",
                    "scope": "demo",
                    "min_relevance": 0.0,
                    "tools": [
                        {
                            "id": "filesystem_read",
                            "name": "Filesystem Read",
                            "description": "Read local files from the workspace",
                            "permissions": ["read_files"],
                            "tokens": 80,
                            "scope": "demo",
                        }
                    ],
                },
            },
        },
        Settings(provider="local"),
    )
    assert response is not None
    text = response["result"]["content"][0]["text"]
    body = json.loads(text)
    assert body["selected"][0]["id"] == "filesystem_read"


def test_mcp_rejects_keys() -> None:
    response = _dispatch(
        {
            "id": 3,
            "method": "tools/call",
            "params": {
                "name": "mcp_select",
                "arguments": {"query": "x", "tools": [], "jev_api_key": "secret"},
            },
        },
        Settings(provider="local"),
    )
    assert response is not None
    assert response["result"]["isError"] is True
    assert "cles" in response["result"]["content"][0]["text"]


def test_cli_demo(capsys) -> None:
    assert main(["demo"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["decision"] == "select"
    ids = {item["id"] for item in out["selected"]}
    assert "filesystem_read" in ids
    assert "github_search" in ids


def test_cli_select(tmp_path, capsys) -> None:
    path = tmp_path / "job.json"
    path.write_text(
        json.dumps(
            {
                "query": "read local files workspace",
                "scope": "demo",
                "min_relevance": 0.0,
                "tools": [
                    {
                        "id": "filesystem_read",
                        "name": "Filesystem Read",
                        "description": "Read local files from the workspace",
                        "permissions": ["read_files"],
                        "tokens": 80,
                        "scope": "demo",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    assert main(["select", "--file", str(path)]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["selected"][0]["id"] == "filesystem_read"


def test_scores_parser() -> None:
    from jev_mcp_router.providers.scores import parse_score_list

    scores = parse_score_list({"scores": [{"id": "a", "confidence": 1.5}]})
    assert scores == {"a": 1.0}


def test_mcp_read_json_line() -> None:
    from jev_mcp_router.mcp_server import _read_message

    raw = json.dumps({"id": 1, "method": "initialize"}).encode("utf-8") + b"\n"
    message = _read_message(io.BytesIO(raw))
    assert message is not None
    assert message["method"] == "initialize"
