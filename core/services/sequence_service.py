"""Service de numerotation atomique."""

from django.db import transaction
from ..models import Sequence


class SequenceService:
    """Compteurs monotones partages, proteges par select_for_update."""

    @staticmethod
    @transaction.atomic
    def next_value(key: str) -> int:
        """
        Retourne la prochaine valeur du compteur identifie par `key`.
        Atomique : deux appels concurrents recoivent des valeurs distinctes.
        """
        seq, _ = Sequence.objects.select_for_update().get_or_create(key=key)
        seq.value += 1
        seq.save(update_fields=['value'])
        return seq.value

    @staticmethod
    def next_bc_numero(annee: int) -> str:
        return f"BC-{annee}-{SequenceService.next_value(f'BC-{annee}'):04d}"

    @staticmethod
    def next_da_reference(annee: int) -> str:
        return f"DA-{annee}-{SequenceService.next_value(f'DA-{annee}'):03d}"

    @staticmethod
    def next_prestataire_code() -> str:
        return f"PREST-{SequenceService.next_value('PREST'):03d}"

    @staticmethod
    def next_tache_numero(exercice_annee: int) -> str:
        return f"T-{SequenceService.next_value(f'T-{exercice_annee}'):03d}"
