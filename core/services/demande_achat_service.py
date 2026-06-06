"""Service metier pour les Demandes d'Achat."""

import logging
from decimal import Decimal
from django.db import transaction
from ..models import DemandeAchat, ExerciceBudgetaire, JournalActivite, LigneBudgetaire
from .notification_service import NotificationService
from .sequence_service import SequenceService

logger = logging.getLogger('budgetpad')


class DemandeAchatService:
    """Logique metier pour les demandes d'achat."""

    @staticmethod
    @transaction.atomic
    def creer(ligne_budgetaire: LigneBudgetaire, objet: str, montant_estime: Decimal,
              utilisateur, reference: str = '', exercice: ExerciceBudgetaire = None,
              nature_prestation: str = '', periode_engagement: str = '',
              priorite: str = '') -> DemandeAchat:
        """
        Crée une demande d'achat liée à une ligne budgétaire.
        - reference : laissez vide pour auto-génération au format DAC{AAMM}DLA{NNNNN}
        """
        exercice = exercice or ligne_budgetaire.tache.exercice
        if exercice is None:
            raise ValueError("Aucun exercice budgétaire actif.")

        if montant_estime is None or montant_estime <= 0:
            raise ValueError("Le montant estimé doit être supérieur à zéro.")

        if not reference:
            reference = SequenceService.next_da_reference()

        da = DemandeAchat.objects.create(
            reference=reference,
            exercice=exercice,
            ligne_budgetaire=ligne_budgetaire,
            objet=objet,
            montant_estime=montant_estime,
            nature_prestation=nature_prestation,
            periode_engagement=periode_engagement,
            priorite=priorite,
            statut='cree',
            created_by=utilisateur,
        )

        JournalActivite.objects.create(
            type_action='DA.create',
            description=f"Création de {reference} — {objet}",
            entite_type='da',
            entite_id=da.id,
            utilisateur=utilisateur,
        )

        # Notifier les valideurs (Directeur DRH + admins)
        tache = ligne_budgetaire.tache
        NotificationService.notifier_roles(
            roles=['directeur_drh', 'admin'],
            type_notif='da_a_valider',
            titre=f"Nouvelle DA à valider : {reference}",
            message=(
                f"{objet} ({montant_estime:,.0f} FCFA) — "
                f"ligne {ligne_budgetaire.code_nature} / tâche {tache.numero}"
            ),
            entite_type='da', entite_id=da.id,
        )
        logger.info("DA créée : %s par %s", reference, utilisateur.username)

        return da
