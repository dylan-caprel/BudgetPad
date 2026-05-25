"""Service métier pour les Virements Budgétaires"""

from decimal import Decimal
from django.db import transaction
from django.db.models import F
from ..models import Tache, VirementBudgetaire, JournalActivite


class VirementService:
    """Logique métier pour Virements"""
    
    @staticmethod
    @transaction.atomic
    def creer_virement(tache_source: Tache, tache_dest: Tache,
                       montant: Decimal, motif: str, 
                       utilisateur) -> VirementBudgetaire:
        """
        Crée un virement avec atomicité garantie.
        
        Args:
            tache_source: Tâche source (argent sort)
            tache_dest: Tâche destination (argent entre)
            montant: Montant en FCFA
            motif: Raison du virement
            utilisateur: Utilisateur qui crée le virement
        
        Returns:
            Instance VirementBudgetaire créée
        
        Raises:
            ValueError: Si validation échoue
        """
        # Validations métier
        if tache_source == tache_dest:
            raise ValueError("Source et destination doivent être différentes")
        
        if montant <= 0:
            raise ValueError("Montant doit être positif")
        
        # Lock pessimiste pour éviter race condition
        source_locked = Tache.objects.select_for_update().get(pk=tache_source.pk)
        
        if montant > source_locked.solde:
            raise ValueError(
                f"Solde insuffisant: {source_locked.solde:,.0f} FCFA disponible"
            )
        
        # Mise à jour atomique avec F()
        Tache.objects.filter(pk=tache_source.pk).update(
            transactions_moins=F('transactions_moins') + montant
        )
        Tache.objects.filter(pk=tache_dest.pk).update(
            transactions_plus=F('transactions_plus') + montant
        )
        
        # Créer le virement
        virement = VirementBudgetaire.objects.create(
            tache_source=tache_source,
            tache_dest=tache_dest,
            montant=montant,
            motif=motif,
            created_by=utilisateur
        )
        
        # Journal
        JournalActivite.objects.create(
            type_action='Virement',
            description=f"{tache_source.numero} → {tache_dest.numero}: {montant:,.0f} FCFA",
            entite_type='virement',
            entite_id=virement.id,
            utilisateur=utilisateur
        )
        
        return virement
