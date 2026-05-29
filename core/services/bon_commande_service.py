"""Service metier pour les Bons de Commande (modèle Tache/LigneBudgetaire/ImputationBC)."""

from decimal import Decimal
from django.utils import timezone
from django.db import transaction
from django.db.models import Sum, Q
from ..models import (
    BonCommande, ExerciceBudgetaire, HistoriqueStatut, JournalActivite,
    Prestataire, Tache, LigneBudgetaire, ImputationBC,
)
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
              demande=None, taux_tva: Decimal = TVA_RATE,
              imputations: list = None) -> BonCommande:
        """
        Cree un BC en garantissant l'integrite budgetaire :
        - lock pessimiste sur la tache (select_for_update)
        - calcul du solde depuis les LIGNES budgétaires (nouvelle structure)
        - verification du solde sous lock (R1)
        - numerotation atomique
        - creation d'ImputationBC (defaut: 1 imputation sur la ligne avec le plus gros solde)
        - journal d'activite (R4)

        Args:
            imputations: liste optionnelle de (ligne_budgetaire, montant) pour répartir
                        manuellement. Si None, impute automatiquement sur la ligne ayant
                        le plus gros solde.
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

        # Récupère les lignes actives annotées (budget_ajuste, consommation, solde par ligne)
        lignes_annotees = list(
            LigneBudgetaire.objects.filter(tache=tache_locked, actif=True)
            .with_aggregates().order_by('-solde', 'code_nature')
        )
        if not lignes_annotees:
            raise ValueError(
                f"La tâche {tache_locked.numero} n'a aucune ligne budgétaire active. "
                f"Créez d'abord au moins une ligne avant d'imputer un BC."
            )

        # Solde global = somme des soldes des lignes actives
        solde_tache = sum((l.solde or Decimal('0')) for l in lignes_annotees)
        if montant_ttc > solde_tache:
            raise ValueError(
                f"Montant TTC ({montant_ttc:,.0f} FCFA) supérieur au solde "
                f"disponible ({solde_tache:,.0f} FCFA) de la tâche {tache_locked.numero}."
            )

        # Validation des imputations explicites si fournies
        if imputations:
            total_imp = sum(Decimal(str(m)) for _, m in imputations)
            if total_imp != montant_ttc:
                raise ValueError(
                    f"Somme des imputations ({total_imp:,.0f}) ≠ montant TTC ({montant_ttc:,.0f})."
                )
            # Vérifie le solde de chaque ligne
            soldes_par_pk = {l.pk: (l.solde or Decimal('0')) for l in lignes_annotees}
            for ligne, montant_imp in imputations:
                disponible = soldes_par_pk.get(ligne.pk)
                if disponible is None:
                    raise ValueError(f"Ligne {ligne.code_nature} introuvable ou inactive.")
                if Decimal(str(montant_imp)) > disponible:
                    raise ValueError(
                        f"Imputation sur {ligne.code_nature} ({montant_imp:,.0f}) "
                        f"supérieure au solde disponible ({disponible:,.0f})."
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

        # Crée les imputations
        if imputations:
            for ligne, montant_imp in imputations:
                ImputationBC.objects.create(
                    bon_commande=bc, ligne_budgetaire=ligne,
                    montant=Decimal(str(montant_imp)),
                )
        else:
            # Auto : impute le montant restant sur les lignes par ordre décroissant de solde
            restant = montant_ttc
            for ligne in lignes_annotees:
                if restant <= 0:
                    break
                ligne_solde = ligne.solde or Decimal('0')
                if ligne_solde <= 0:
                    continue
                montant_imp = min(restant, ligne_solde)
                ImputationBC.objects.create(
                    bon_commande=bc, ligne_budgetaire=ligne, montant=montant_imp,
                )
                restant -= montant_imp

        # Si rattache a une DA, marquer celle-ci comme 'bc_cree'
        if demande is not None and demande.statut != 'bc_cree':
            demande.statut = 'bc_cree'
            demande.save(update_fields=['statut'])

        JournalActivite.objects.create(
            type_action='BC.create',
            description=f"Création du BC {numero} ({montant_ttc:,.0f} FCFA)",
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
