"""
Politique de retention du journal d'activite (RGPD).

Supprime les entrees plus anciennes que --days (defaut 1825 = 5 ans).
La chaine de hash est reconstruite a partir des entrees restantes.

Usage :
    python manage.py purge_journal --days 1825 --confirm
"""

from datetime import timedelta
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.models import JournalActivite


class Command(BaseCommand):
    help = "Purge le journal d'activite passe un certain age (politique de retention RGPD)."

    def add_arguments(self, parser):
        parser.add_argument('--days', type=int, default=1825,
                            help='Age maximum en jours (defaut: 1825 = 5 ans).')
        parser.add_argument('--confirm', action='store_true',
                            help='Confirme l\'execution (sinon dry-run).')

    def handle(self, *args, **options):
        days = options['days']
        confirm = options['confirm']
        cutoff = timezone.now() - timedelta(days=days)

        qs = JournalActivite.objects.filter(created_at__lt=cutoff)
        nb = qs.count()

        if nb == 0:
            self.stdout.write(self.style.SUCCESS(
                f"Aucune entree plus ancienne que {days} jours."
            ))
            return

        self.stdout.write(self.style.WARNING(
            f"{nb} entree(s) antérieure(s) au {cutoff.date()} "
            f"({days} jours) seront supprime(s)."
        ))

        if not confirm:
            self.stdout.write(self.style.WARNING(
                "Mode dry-run. Ajoutez --confirm pour appliquer."
            ))
            return

        deleted, _ = qs.delete()
        self.stdout.write(self.style.SUCCESS(f"[OK] {deleted} entree(s) supprime(s)."))

        # Reconstruire la chaine sur les entrees restantes
        self.stdout.write("Reconstruction de la chaine de hash...")
        call_command('rebuild_audit_chain', '--confirm', verbosity=0)
        self.stdout.write(self.style.SUCCESS("[OK] Chaine reconstruite."))
