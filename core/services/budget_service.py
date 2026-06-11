"""Service métier pour les calculs budgétaires transverses.

Point de vérité UNIQUE pour le solde disponible d'une ligne budgétaire.
Avant ce service, le même calcul (requête annotée + réintégration éventuelle)
était dupliqué dans 4 vues — source avérée de divergences (cf. docs/audit_technique.md, C3).
"""
from decimal import Decimal

from ..models import ConsommationDirecte, LigneBudgetaire


class BudgetService:
    """Calculs de solde partagés par les vues consommations / virements / lignes."""

    @staticmethod
    def solde_disponible(ligne_id: int, reintegrer_conso_id: int | None = None) -> Decimal:
        """Solde réel d'une ligne budgétaire (budget ajusté − consommations).

        Args:
            ligne_id: pk de la LigneBudgetaire.
            reintegrer_conso_id: pk d'une ConsommationDirecte en cours d'édition,
                dont l'ancien montant doit être réintégré au disponible (sinon
                l'édition d'une consommation se bloquerait elle-même).

        Returns:
            Le solde disponible (Decimal, jamais None).
        """
        ligne = LigneBudgetaire.objects.with_aggregates().get(pk=ligne_id)
        dispo = ligne.solde or Decimal('0')
        if reintegrer_conso_id:
            ancien = (
                ConsommationDirecte.objects
                .filter(pk=reintegrer_conso_id, est_annule=False)
                .values_list('montant', flat=True)
                .first()
            )
            dispo += ancien or Decimal('0')
        return dispo
