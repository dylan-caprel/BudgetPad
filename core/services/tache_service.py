"""Service métier pour les Tâches Budgétaires"""

from decimal import Decimal
from django.db.models import Sum, Q
from ..models import Tache, Alerte
from ..constants import ALERTE_SEUIL_DANGER


class TacheService:
    """Logique métier pour Tâches"""
    
    @staticmethod
    def verifier_alertes(tache: Tache, seuil: int = ALERTE_SEUIL_DANGER) -> None:
        """
        Vérifie si une tâche dépasse le seuil et crée une alerte.
        
        Args:
            tache: Instance Tache
            seuil: Seuil en pourcentage (défaut: 90%)
        """
        taux = float(tache.taux_consommation)
        if taux >= seuil:
            exists = Alerte.objects.filter(
                tache=tache, 
                seuil_atteint=Decimal(str(taux))
            ).exists()
            
            if not exists:
                Alerte.objects.create(
                    tache=tache,
                    type_alerte='seuil_atteint',
                    message=f"{tache.numero} {tache.titre} — taux {taux} %",
                    seuil_atteint=Decimal(str(taux))
                )
    
    @staticmethod
    def get_taux_couleur(taux_consommation: float) -> str:
        """Retourne la couleur pour un taux de consommation"""
        if taux_consommation >= 90:
            return 'danger'
        elif taux_consommation >= 70:
            return 'warning'
        return 'success'
