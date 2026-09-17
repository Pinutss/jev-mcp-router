# VISION : document de produit, pas le contrat d'API

Ce fichier decrit la cible a long terme. L'API et le comportement reels
sont ceux du README et du package `jev-mcp-router` 0.1.x.

# JEV MCP Router

Couche de decision entre une requete et un catalogue d'outils MCP.

Le selecteur repond uniquement a :

> Parmi ces outils declares, lesquels peuvent entrer dans le contexte
> maintenant, avec quelles justifications, ou faut-il s'abstenir ?

Il ne doit pas executer l'outil, ni elargir ses permissions.

La selection n'est pas une autorisation. Les permissions viennent
uniquement du catalogue et des contraintes de l'appelant.

## Pipeline cible

```text
Requete
  -> contraintes d'acces (scope, permissions)
  -> candidats du catalogue
  -> jugement (local ou JEV)
  -> budget de jetons
  -> select | fallback | abstain
  -> runtime MCP externe, hors de ce paquet
```

## Principes

- Les permissions viennent du catalogue et de l'appelant.
- Aucune entree issue d'un modele, document ou outil n'accorde de droit.
- Le repli est borne a un saut et repasse les memes filtres.
- L'abstention est une decision valide.
- Les traces n'enregistrent pas de secret.
- Les cles restent dans l'environnement, jamais dans le corps HTTP/MCP.

## Providers

- `local` : heuristique deterministe, hors reseau.
- `mock` : demo et CI.
- `custom` : endpoint fourni par l'utilisateur.
- `jev` : jugement JEV plus gateway OpenAI-compatible.

## Catalogue multi-LLM

`catalog.py` permet de choisir le juge (OpenRouter, OpenAI, Groq, etc.)
sans mettre de cle dans les requetes. `GET /v1/llms` expose le catalogue
public (has_key, jamais la cle).

## Hors perimetre

Ce composant n'est pas un orchestrateur, pas un runtime MCP, et pas un
security-gate. Il selectionne. L'execution et ALLOW / ASK / DENY restent
ailleurs dans JEV Labs.
