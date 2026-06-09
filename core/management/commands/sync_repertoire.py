"""Alimente le répertoire (catalogue réutilisable de tâches/lignes) depuis un exercice.

Le répertoire sert au wizard de création d'exercice : il évite de ressaisir la
nomenclature DRH chaque année.

Usage :
    python manage.py sync_repertoire              # depuis l'exercice actif
    python manage.py sync_repertoire --annee 2026 # depuis un exercice précis
"""
from django.core.management.base import BaseCommand, CommandError

from core.models import ExerciceBudgetaire
from core.services.repertoire_service import sync_repertoire_from_exercice


class Command(BaseCommand):
    help = "Alimente le répertoire (catalogue tâches/lignes) depuis un exercice."

    def add_arguments(self, parser):
        parser.add_argument('--annee', type=int, default=None,
                            help="Année de l'exercice source (défaut : exercice actif).")

    def handle(self, *args, **options):
        annee = options.get('annee')
        if annee:
            exercice = ExerciceBudgetaire.objects.filter(annee=annee).first()
            if not exercice:
                raise CommandError(f"Aucun exercice {annee} trouvé.")
        else:
            exercice = ExerciceBudgetaire.get_actif()
            if not exercice:
                raise CommandError("Aucun exercice actif. Précisez --annee.")

        nb_taches, nb_lignes = sync_repertoire_from_exercice(exercice)
        self.stdout.write(self.style.SUCCESS(
            f"Repertoire alimente depuis l'exercice {exercice.annee} : "
            f"{nb_taches} taches / {nb_lignes} lignes."
        ))
