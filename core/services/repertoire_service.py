"""Service du répertoire (catalogue réutilisable de tâches/lignes pour les exercices).

Le répertoire (RepertoireTache / RepertoireLigne) alimente le wizard de création
d'exercice : il permet de réutiliser la nomenclature DRH d'une année sur l'autre
sans tout ressaisir.
"""
from ..models import Tache, LigneBudgetaire, RepertoireTache, RepertoireLigne


def sync_repertoire_from_exercice(exercice):
    """Verse toutes les tâches/lignes ACTIVES d'un exercice dans le répertoire global.

    Idempotent (update_or_create). Retourne (nb_taches, nb_lignes).
    """
    nb_taches = nb_lignes = 0
    for tache in Tache.objects.filter(exercice=exercice, actif=True).order_by('numero'):
        rep_tache, _ = RepertoireTache.objects.update_or_create(
            numero=tache.numero,
            defaults={'titre': tache.titre, 'actif': True},
        )
        nb_taches += 1
        for ligne in LigneBudgetaire.objects.filter(tache=tache, actif=True).order_by('code_nature'):
            RepertoireLigne.objects.update_or_create(
                tache_repertoire=rep_tache,
                code_nature=ligne.code_nature,
                defaults={'libelle_nature': ligne.libelle_nature, 'actif': True},
            )
            nb_lignes += 1
    return nb_taches, nb_lignes
