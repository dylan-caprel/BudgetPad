"""
Verifie l'integrite de la chaine de hash du JournalActivite.

Usage : python manage.py verify_audit_chain
"""

from django.core.management.base import BaseCommand
from core.models import JournalActivite


class Command(BaseCommand):
    help = "Verifie l'integrite cryptographique du journal d'activite (hash chaine)."

    def handle(self, *args, **options):
        entries = list(JournalActivite.objects.order_by('pk'))
        if not entries:
            self.stdout.write(self.style.WARNING("Journal vide."))
            return

        nb_total = len(entries)
        prev_hash = ''
        broken = []

        for i, entry in enumerate(entries, 1):
            # Verifier le chainage : prev_hash de cette entree doit etre le hash de la precedente
            if entry.prev_hash != prev_hash:
                broken.append((entry.pk, 'prev_hash incoherent',
                               f"attendu={prev_hash[:12]}... obtenu={entry.prev_hash[:12]}..."))

            # Recalculer le hash et comparer
            recomputed = entry.compute_hash()
            if entry.hash_chain != recomputed:
                broken.append((entry.pk, 'hash_chain altere',
                               f"stocke={entry.hash_chain[:12]}... calcule={recomputed[:12]}..."))

            prev_hash = entry.hash_chain

        if broken:
            self.stdout.write(self.style.ERROR(
                f"\n[KO] {len(broken)} anomalie(s) detectee(s) sur {nb_total} entree(s) :\n"
            ))
            for pk, reason, detail in broken:
                self.stdout.write(self.style.ERROR(
                    f"  - id={pk} : {reason} ({detail})"
                ))
            return

        self.stdout.write(self.style.SUCCESS(
            f"[OK] Chaine valide : {nb_total} entree(s), aucune alteration detectee."
        ))
        if entries:
            self.stdout.write(
                f"     Premiere entree (#{entries[0].pk}) prev_hash = {entries[0].prev_hash or 'GENESIS'}"
            )
            self.stdout.write(
                f"     Derniere entree (#{entries[-1].pk}) hash_chain = {entries[-1].hash_chain[:16]}..."
            )
