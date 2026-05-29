"""Service métier pour les Virements Budgétaires (entre lignes budgétaires)."""

from decimal import Decimal
from django.db import transaction
from ..models import LigneBudgetaire, VirementBudgetaire, JournalActivite


class VirementService:

    @staticmethod
    @transaction.atomic
    def creer_virement(
        ligne_source: LigneBudgetaire,
        ligne_destination: LigneBudgetaire,
        montant: Decimal,
        motif: str,
        utilisateur,
        exercice=None,
    ) -> VirementBudgetaire:
        """
        Crée un virement budgétaire entre deux lignes budgétaires.

        Raises:
            ValueError: si la validation échoue (lignes identiques, montant nul, solde insuffisant).
        """
        if ligne_source.pk == ligne_destination.pk:
            raise ValueError("La ligne source et destination doivent être différentes.")

        if montant <= 0:
            raise ValueError("Le montant doit être positif.")

        # Calcul du solde de la ligne source (avec lock pessimiste)
        ligne_locked = (
            LigneBudgetaire.objects.with_aggregates().select_for_update().get(pk=ligne_source.pk)
        )
        solde_source = getattr(ligne_locked, 'solde', None)
        if solde_source is not None and montant > solde_source:
            raise ValueError(
                f"Solde insuffisant sur la ligne source {ligne_source.code_nature} : "
                f"{solde_source:,.0f} FCFA disponible."
            )

        # Déterminer l'exercice
        if exercice is None:
            exercice = ligne_source.tache.exercice

        virement = VirementBudgetaire.objects.create(
            exercice=exercice,
            ligne_source=ligne_source,
            ligne_destination=ligne_destination,
            montant=montant,
            motif=motif,
            created_by=utilisateur,
        )

        JournalActivite.objects.create(
            type_action='Virement',
            description=(
                f"Virement {ligne_source.code_nature} → {ligne_destination.code_nature} : "
                f"{montant:,.0f} FCFA — {motif[:80]}"
            ),
            entite_type='virement',
            entite_id=virement.pk,
            utilisateur=utilisateur,
        )

        return virement
