"""Service metier pour les Demandes d'Achat."""

import logging
from decimal import Decimal
from django.db import transaction
from ..models import DemandeAchat, ExerciceBudgetaire, JournalActivite, Tache
from .notification_service import NotificationService
from .sequence_service import SequenceService

logger = logging.getLogger('budgetpad')


class DemandeAchatService:
    """Logique metier pour les demandes d'achat."""

    @staticmethod
    @transaction.atomic
    def creer(tache: Tache, objet: str, montant_estime: Decimal,
              utilisateur, exercice: ExerciceBudgetaire = None) -> DemandeAchat:
        """
        Cree une demande d'achat avec numerotation atomique et journal.
        """
        if exercice is None:
            exercice = ExerciceBudgetaire.get_actif()
            if exercice is None:
                raise ValueError("Aucun exercice budgetaire actif.")

        if montant_estime is None or montant_estime <= 0:
            raise ValueError("Le montant estime doit etre superieur a zero.")

        reference = SequenceService.next_da_reference(exercice.annee)
        da = DemandeAchat.objects.create(
            reference=reference,
            exercice=exercice,
            tache=tache,
            objet=objet,
            montant_estime=montant_estime,
            statut='cree',
            created_by=utilisateur,
        )

        JournalActivite.objects.create(
            type_action='DA.create',
            description=f"Creation de {reference} - {objet}",
            entite_type='da',
            entite_id=da.id,
            utilisateur=utilisateur,
        )

        # Notifier les valideurs (Directeur DRH + admins)
        NotificationService.notifier_roles(
            roles=['directeur_drh', 'admin'],
            type_notif='da_a_valider',
            titre=f"Nouvelle DA a valider : {reference}",
            message=f"{objet} ({montant_estime:,.0f} FCFA) - tache {tache.numero}",
            entite_type='da', entite_id=da.id,
        )
        logger.info("DA creee : %s par %s", reference, utilisateur.username)

        return da
