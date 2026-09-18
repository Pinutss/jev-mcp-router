---
name: jev-mcp-router
description: Selects MCP tools that fit the query inside a context budget, without executing them. Use when many MCP tools are available and only a budgeted subset should be exposed.
---

# JEV MCP Router

Call the `mcp_select` MCP tool. Do not put API keys in the tool arguments.

Required arguments: `query`, `tools`.

`JEV_PROVIDER` defaults to `local`. The tool ranks or filters candidates. It does not generate user-facing text and it does not execute the selected item.

Keys stay in the process environment.
