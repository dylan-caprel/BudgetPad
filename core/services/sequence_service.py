"""Service de numerotation atomique."""

import re
from django.db import transaction
from ..models import Sequence


class SequenceService:
    """Compteurs monotones partages, proteges par select_for_update.

    Self-healing : avant chaque numerotation metier (DA/BC/Prestataire),
    la sequence est synchronisee avec le max existant en DB. Cela permet de
    creer des entites directement (seed, import) sans passer par le service,
    sans casser la numerotation ulterieure.
    """

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
    def _ensure_sync(key: str, model, field: str, prefix: str, pattern: str) -> None:
        """
        S'assure que la Sequence `key` est >= au max numerique existant dans
        `model.field` pour les valeurs matchant `pattern` (groupe 1 = nombre).
        """
        existing = model.objects.filter(**{f'{field}__startswith': prefix}).values_list(field, flat=True)
        max_n = 0
        rx = re.compile(pattern)
        for n in existing:
            m = rx.match(n)
            if m:
                try:
                    max_n = max(max_n, int(m.group(1)))
                except ValueError:
                    continue
        if max_n > 0:
            with transaction.atomic():
                seq, _ = Sequence.objects.select_for_update().get_or_create(key=key)
                if seq.value < max_n:
                    seq.value = max_n
                    seq.save(update_fields=['value'])

    @staticmethod
    def next_bc_numero(annee: int) -> str:
        from ..models import BonCommande
        SequenceService._ensure_sync(
            key=f'BC-{annee}', model=BonCommande, field='numero',
            prefix=f'BC-{annee}-', pattern=rf'^BC-{annee}-(\d+)$',
        )
        return f"BC-{annee}-{SequenceService.next_value(f'BC-{annee}'):04d}"

    @staticmethod
    def next_da_reference(annee: int) -> str:
        from ..models import DemandeAchat
        SequenceService._ensure_sync(
            key=f'DA-{annee}', model=DemandeAchat, field='reference',
            prefix=f'DA-{annee}-', pattern=rf'^DA-{annee}-(\d+)$',
        )
        return f"DA-{annee}-{SequenceService.next_value(f'DA-{annee}'):03d}"

    @staticmethod
    def next_prestataire_code() -> str:
        from ..models import Prestataire
        SequenceService._ensure_sync(
            key='PREST', model=Prestataire, field='code',
            prefix='PREST-', pattern=r'^PREST-(\d+)$',
        )
        return f"PREST-{SequenceService.next_value('PREST'):03d}"

    @staticmethod
    def next_tache_numero(exercice_annee: int) -> str:
        from ..models import Tache
        SequenceService._ensure_sync(
            key=f'T-{exercice_annee}', model=Tache, field='numero',
            prefix='T-', pattern=r'^T-(\d+)$',
        )
        return f"T-{SequenceService.next_value(f'T-{exercice_annee}'):03d}"
