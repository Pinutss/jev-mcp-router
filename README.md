# jev-mcp-router

Selection des outils MCP pertinents dans un budget de contexte.

Auteur : [Pinuts](https://github.com/Pinutss). Licence MIT.

Fait partie de [JEV Labs](https://github.com/Pinutss/jev-labs).

Stack : Python 3.10+, HTTP, MCP stdio, Docker, HTML de demo.

Apres `jev-mcp serve` : [demo](http://127.0.0.1:8080/)

## Local, sans cle

```bash
git clone https://github.com/Pinutss/jev-mcp-router
cd jev-mcp-router
uv sync
uv run jev-mcp demo
uv run jev-mcp serve
```

`provider=local` par defaut si tu ne mets pas de cles. Docker :

```bash
docker compose up
```

## Ce que fait le prototype

Le selecteur choisit des outils dans un catalogue, sous un budget de
jetons. Il justifie, s'abstient s'il n'y a pas de candidat sur, et
n'autorise qu'un seul saut de repli.

Il n'execute pas les outils et ne les fournit pas.

La selection n'est pas une autorisation. Les permissions viennent
uniquement du catalogue et des contraintes de l'appelant. La tache, un
outil ou un modele ne peuvent pas en ajouter.

## Python

```python
from jev_mcp_router import McpSelector, DEFAULT_TOOLS

result = McpSelector(provider="local").select(
    query="Lire un fichier local puis chercher des issues GitHub",
    tools=DEFAULT_TOOLS,
    max_tools=2,
    budget_tokens=250,
    scope="demo",
)
print(result.decision, [item.id for item in result.selected])
```

## Hermes et OpenClaw

Oui, en local. Le process MCP n'a pas besoin de JEV ni de gateway :

```bash
uv run jev-mcp mcp
```

Un tool : `mcp_select`. Tu lui passes `query` + `tools`. Tes cles restent
dans l'environnement du process, pas dans l'appel.

**Hermes** (`~/.hermes/config.yaml`) :

```yaml
mcp_servers:
  jev-mcp:
    command: uv
    args: ["run", "--directory", "/chemin/vers/jev-mcp-router", "jev-mcp", "mcp"]
    env:
      JEV_PROVIDER: local
```

**OpenClaw** (`~/.openclaw/openclaw.json`, ou Settings > MCP > Stdio) :

```json
{
  "mcp": {
    "servers": {
      "jev-mcp": {
        "command": "uv",
        "args": ["run", "--directory", "/chemin/vers/jev-mcp-router", "jev-mcp", "mcp"],
        "env": { "JEV_PROVIDER": "local" }
      }
    }
  }
}
```

Exemples prets a copier : `examples/hermes.yaml`, `examples/openclaw.json`.

## JEV + gateway (optionnel)

Si tu branches le cloud plus tard, deux cles suffisent : `JEV_API_KEY` /
`JEV_BASE_URL`, et ta gateway. Si `GATEWAY_*` est incomplet, le catalogue
multi-LLM resout le juge (`OPENROUTER_API_KEY`, `OPENAI_API_KEY`, etc.).

Pas de cle dans le corps HTTP ou MCP.

```bash
cp .env.example .env
```

`JEV_PROVIDER=jev` refuse de demarrer si JEV ou la gateway resolue manque.

Catalogue public : `GET /v1/llms`. Exemple JSON : `examples/models.json`.

## HTTP

```bash
uv run jev-mcp serve
```

`GET /`, `/demo`, `/healthz`, `/v1/llms`. `POST /v1/select`. Bind
`127.0.0.1`. Le body ne contient pas de cles. Il peut contenir
`gateway_provider`, `gateway_model`, `llm_prefer`.

## Validation locale

```bash
uv run jev-mcp benchmark
```

Jeu annote dans `benchmarks/annotated_tasks.json`. C'est une baseline
locale, pas un essai JEV reel.

## Limites

Le tri local est lexical et deterministe. Le scope isole des listes, ce
n'est pas une auth. Un seul saut de repli. Pas d'execution d'outil. Pas
de store, pas de PyPI pour l'instant.

`docs/vision.md` est une cible longue, pas le contrat actuel.
