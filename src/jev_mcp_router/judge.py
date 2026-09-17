"""Point d'extension interne pour un juge externe.

Ce protocole n'est pas exporte. HeuristicSelector et les providers
JEV / gateway couvrent le classement public.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .models import SelectRequest, ToolProfile


class Judge(Protocol):
    """Reordonne des candidats deja filtres et valides.

    Contrat attendu : sortie deterministe pour une entree donnee, aucun
    effet de bord, aucune elevation de permissions. Un juge ne peut pas
    reintroduire un outil rejete par les regles d'acces.
    """

    def rerank(
        self,
        request: SelectRequest,
        candidates: Sequence[ToolProfile],
    ) -> Sequence[tuple[ToolProfile, float, tuple[str, ...]]]:
        """Retourne les candidats ordonnes, avec score et justification."""
        ...
