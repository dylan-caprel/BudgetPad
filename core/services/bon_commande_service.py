"""Service metier pour les Bons de Commande."""

from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Q
from ..models import BonCommande, ExerciceBudgetaire, HistoriqueStatut, JournalActivite, Prestataire, Tache
from ..constants import TVA_RATE
from .sequence_service import SequenceService


class BonCommandeService:
    """Logique metier pour Bons de Commande."""

    # ------------------------------------------------------------------ TVA

    @staticmethod
    def calculer_montants_avec_tva(montant_ht: Decimal, taux_tva: Decimal = TVA_RATE) -> dict:
        """Retourne {'montant_ht', 'montant_tva', 'montant_ttc'} arrondis."""
        montant_tva = (montant_ht * taux_tva / Decimal('100')).quantize(Decimal('0.01'))
        montant_ttc = montant_ht + montant_tva
        return {
            'montant_ht': montant_ht,
            'montant_tva': montant_tva,
            'montant_ttc': montant_ttc,
        }

    # -------------------------------------------------------------- CREATION

    @staticmethod
    @transaction.atomic
    def creer(tache: Tache, prestataire: Prestataire, montant_ht: Decimal,
              utilisateur, exercice: ExerciceBudgetaire = None,
              demande=None, taux_tva: Decimal = TVA_RATE) -> BonCommande:
        """
        Cree un BC en garantissant l'integrite budgetaire :
        - lock pessimiste sur la tache (select_for_update)
        - verification du solde sous lock
        - numerotation atomique
        - journal d'activite
        """
        if exercice is None:
            exercice = ExerciceBudgetaire.get_actif()
            if exercice is None:
                raise ValueError("Aucun exercice budgetaire actif.")

        if montant_ht is None or montant_ht <= 0:
            raise ValueError("Le montant HT doit etre superieur a zero.")

        montants = BonCommandeService.calculer_montants_avec_tva(montant_ht, taux_tva)
        montant_ttc = montants['montant_ttc']

        # Lock pessimiste sur la tache pour eviter les depassements concurrents
        tache_locked = Tache.objects.select_for_update().get(pk=tache.pk)

        # Recalcul du solde sous lock (la propriete .solde fait une agregation)
        budget_ajuste = (
            tache_locked.montant_initial
            + tache_locked.transactions_plus
            - tache_locked.transactions_moins
        )
        consommation = (
            BonCommande.objects.filter(tache=tache_locked)
            .exclude(statut='annule')
            .aggregate(s=Sum('montant_ttc'))['s']
        ) or Decimal('0')
        solde = budget_ajuste - consommation

        if montant_ttc > solde:
            raise ValueError(
                f"Montant TTC ({montant_ttc:,.0f} FCFA) superieur au solde "
                f"disponible ({solde:,.0f} FCFA) de la tache {tache_locked.numero}."
            )

        numero = SequenceService.next_bc_numero(exercice.annee)

        bc = BonCommande.objects.create(
            numero=numero,
            demande=demande,
            tache=tache_locked,
            exercice=exercice,
            prestataire=prestataire,
            direction='Direction des Ressources Humaines',
            taux_tva=taux_tva,
            montant_ht=montant_ht,
            montant_tva=montants['montant_tva'],
            montant_ttc=montant_ttc,
            statut='cree',
        )

        # Si rattache a une DA, marquer celle-ci comme 'bc_cree'
        if demande is not None and demande.statut != 'bc_cree':
            demande.statut = 'bc_cree'
            demande.save(update_fields=['statut'])

        JournalActivite.objects.create(
            type_action='BC.create',
            description=f"Creation du BC {numero}",
            entite_type='bc',
            entite_id=bc.id,
            utilisateur=utilisateur,
        )

        return bc

    # --------------------------------------------------------- TRANSITIONS

    @staticmethod
    def peut_transiter(bc: BonCommande, nouveau_statut: str) -> bool:
        """Verifie si la transition de statut est autorisee."""
        return nouveau_statut in bc.TRANSITIONS.get(bc.statut, [])

    @staticmethod
    @transaction.atomic
    def changer_statut(bc: BonCommande, nouveau_statut: str,
                       utilisateur, motif: str = '') -> dict:
        """
        Change le statut d'un BC avec historique + journal complet.
        Renvoie {'success': True, 'message': str}. Leve ValueError si invalide.
        """
        peut, msg = bc.peut_transiter_vers(nouveau_statut)
        if not peut:
            raise ValueError(msg)

        ancien_statut = bc.statut
        update_fields = ['statut']

        if nouveau_statut == 'notifie':
            bc.date_notification = timezone.now().date()
            update_fields.append('date_notification')
        elif nouveau_statut == 'annule':
            bc.motif_annulation = motif or 'Non specifie'
            update_fields.append('motif_annulation')

        bc.statut = nouveau_statut
        bc.save(update_fields=update_fields)

        HistoriqueStatut.objects.create(
            type_entite='BC',
            entite_id=bc.id,
            ancien_statut=ancien_statut,
            nouveau_statut=nouveau_statut,
            utilisateur=utilisateur,
            commentaire=motif,
        )

        action_map = {
            'notifie': 'BC.notify',
            'en_cours': 'BC.start',
            'execute': 'BC.execute',
            'annule': 'BC.cancel',
        }
        JournalActivite.objects.create(
            type_action=action_map.get(nouveau_statut, 'BC.create'),
            description=f"BC {bc.numero}: {ancien_statut} -> {nouveau_statut}",
            entite_type='bc',
            entite_id=bc.id,
            utilisateur=utilisateur,
        )

        return {'success': True, 'message': f"BC {bc.numero} -> {nouveau_statut}"}
