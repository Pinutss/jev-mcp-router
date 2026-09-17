"""Erreurs publiques du selecteur MCP."""


class RouterError(Exception):
    """Erreur de base du selecteur."""


class ConfigurationError(RouterError):
    """Configuration manquante ou invalide."""


class ProviderError(RouterError):
    """Echec d'un provider distant."""
