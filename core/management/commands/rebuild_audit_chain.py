"""
Reconstruit la chaine de hash sur des entrees existantes (typiquement apres
une migration ajoutant les champs hash_chain / prev_hash).

ATTENTION : a n'utiliser qu'une seule fois, juste apres l'introduction du
schema. En operation normale, le chainage est gere par save().

Usage : python manage.py rebuild_audit_chain --confirm
"""

from django.core.management.base import BaseCommand
from core.models import JournalActivite


class Command(BaseCommand):
    help = "Reconstruit la chaine de hash JournalActivite (operation de migration unique)."

    def add_arguments(self, parser):
        parser.add_argument('--confirm', action='store_true',
                            help='Confirme l\'execution (sans cela, dry-run).')

    def handle(self, *args, **options):
        confirm = options['confirm']
        entries = list(JournalActivite.objects.order_by('pk'))
        if not entries:
            self.stdout.write("Journal vide, rien a faire.")
            return

        prev = ''
        updates = 0
        for entry in entries:
            entry.prev_hash = prev
            new_hash = entry.compute_hash()
            if entry.hash_chain != new_hash:
                updates += 1
                if confirm:
                    JournalActivite.objects.filter(pk=entry.pk).update(
                        prev_hash=prev, hash_chain=new_hash,
                    )
            prev = new_hash

        if confirm:
            self.stdout.write(self.style.SUCCESS(
                f"[OK] {updates} entree(s) re-scellee(s) sur {len(entries)}."
            ))
        else:
            self.stdout.write(self.style.WARNING(
                f"[DRY-RUN] {updates} entree(s) seraient mises a jour sur {len(entries)}."
            ))
            self.stdout.write("Relancer avec --confirm pour appliquer.")
