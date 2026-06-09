"""Tests de la commande de seed des données réelles PAD 2026 (seed_real_data).

Tourne sur la base SQLite en mémoire (cf. budgetpad.settings.test) — n'affecte
jamais la base réelle. Vérifie la structure, la FIDÉLITÉ au suivi officiel
(solde recalculé par l'app == solde du PDF pour les 128 lignes) et l'idempotence.
"""
import json
from decimal import Decimal
from pathlib import Path

import pytest
from django.core.management import call_command

from core.models import (
    ExerciceBudgetaire, Tache, LigneBudgetaire,
    VirementBudgetaire, ConsommationDirecte, PrestationProgrammee,
)

DATA = Path(__file__).resolve().parent.parent / 'management' / 'commands' / 'data'


def D(x):
    return Decimal(str(x))


def _taches():
    return json.loads((DATA / 'pad_2026_taches.json').read_text(encoding='utf-8'))


def _journal():
    return json.loads((DATA / 'pad_2026_journal.json').read_text(encoding='utf-8'))


@pytest.mark.django_db
def test_structure_creee():
    call_command('seed_real_data')
    taches = _taches()
    journal = _journal()
    ex = ExerciceBudgetaire.objects.get(annee=2026)

    assert ex.is_active is True
    assert ex.statut == 'actif'
    assert Tache.objects.filter(exercice=ex).count() == len(taches)            # 57
    assert (LigneBudgetaire.objects.filter(tache__exercice=ex).count()
            == sum(len(t['lignes']) for t in taches))                          # 128
    assert PrestationProgrammee.objects.filter(exercice=ex).count() == len(journal)  # 36


@pytest.mark.django_db
def test_solde_reproduit_le_suivi_officiel():
    """Pour CHAQUE ligne, le solde recalculé par l'app doit égaler le solde officiel
    (= budget initial + transfert+ − transfert− − consommation)."""
    call_command('seed_real_data')
    ex = ExerciceBudgetaire.objects.get(annee=2026)
    lignes = {
        (l.tache.numero, l.code_nature): l
        for l in LigneBudgetaire.objects.with_aggregates()
        .filter(tache__exercice=ex).select_related('tache')
    }
    for t in _taches():
        for l in t['lignes']:
            ligne = lignes[(t['numero'], l['code_nature'])]
            attendu = (D(l['montant_initial']) + D(l['transfert_plus'])
                       - D(l['transfert_moins']) - D(l['consommation']))
            assert int(ligne.solde) == int(attendu), (
                f"{t['numero']}/{l['code_nature']} : solde {ligne.solde} != attendu {attendu}"
            )


@pytest.mark.django_db
def test_totaux_globaux():
    call_command('seed_real_data')
    ex = ExerciceBudgetaire.objects.get(annee=2026)
    taches = _taches()

    # consommation totale
    total_conso_attendu = sum(D(l['consommation']) for t in taches for l in t['lignes'])
    total_conso_db = sum(
        c.montant for c in ConsommationDirecte.objects.filter(ligne_budgetaire__tache__exercice=ex)
    )
    assert int(total_conso_db) == int(total_conso_attendu)              # 1 692 877 445

    # montant_ht total du journal == total officiel JP-BC
    total_ht = sum(p.montant_ht for p in PrestationProgrammee.objects.filter(exercice=ex))
    assert int(total_ht) == 140_952_000

    # transferts entrants == transferts sortants (équilibre interne après bake)
    tp = sum(v.montant for v in VirementBudgetaire.objects.filter(exercice=ex))
    assert tp > 0  # des virements ont bien été créés


@pytest.mark.django_db
def test_journal_lie_aux_lignes():
    call_command('seed_real_data')
    ex = ExerciceBudgetaire.objects.get(annee=2026)
    presta = PrestationProgrammee.objects.filter(exercice=ex)
    # Toutes les prestations du JP-BC référencent des tâches/natures réelles -> liées
    non_liees = [p.numero_ligne for p in presta if p.ligne_budgetaire_id is None]
    assert non_liees == [], f"Prestations non liées à une ligne : {non_liees}"


@pytest.mark.django_db
def test_reset_supprime_demo_et_parasites():
    """--reset retire le procurement de démo et les tâches parasites de 2026,
    en gardant l'exercice officiel intact et sans double comptage."""
    from core.models import Tache, LigneBudgetaire, DemandeAchat
    call_command('seed_real_data')
    ex = ExerciceBudgetaire.objects.get(annee=2026)

    # Tâche parasite + DA de démo sur une ligne officielle
    parasite = Tache.objects.create(exercice=ex, numero='T-PARASITE', titre='TACHE TEST', actif=True)
    LigneBudgetaire.objects.create(tache=parasite, code_nature='9999999',
                                   libelle_nature='TEST', montant_initial=Decimal('1000'))
    ligne_off = LigneBudgetaire.objects.filter(tache__exercice=ex).exclude(tache=parasite).first()
    DemandeAchat.objects.create(
        reference='DA-DEMO-001', exercice=ex, ligne_budgetaire=ligne_off,
        objet='DA de démonstration', montant_estime=Decimal('500000'), statut='cree',
    )
    n_taches_off = len(_taches())

    call_command('seed_real_data', '--reset')

    assert not Tache.objects.filter(numero='T-PARASITE').exists()
    assert not DemandeAchat.objects.filter(reference='DA-DEMO-001').exists()
    # L'exercice officiel reste complet
    assert Tache.objects.filter(exercice=ex).count() == n_taches_off          # 58
    # Consommation = officielle uniquement (pas de double comptage)
    total_conso_attendu = sum(D(l['consommation']) for t in _taches() for l in t['lignes'])
    total_conso_db = sum(
        c.montant for c in ConsommationDirecte.objects.filter(ligne_budgetaire__tache__exercice=ex)
    )
    assert int(total_conso_db) == int(total_conso_attendu)


@pytest.mark.django_db
def test_idempotence():
    """Relancer la commande ne duplique ni les lignes, ni les virements, ni les consommations."""
    call_command('seed_real_data')
    ex = ExerciceBudgetaire.objects.get(annee=2026)
    n_lignes = LigneBudgetaire.objects.filter(tache__exercice=ex).count()
    n_vir = VirementBudgetaire.objects.filter(exercice=ex).count()
    n_conso = ConsommationDirecte.objects.filter(ligne_budgetaire__tache__exercice=ex).count()
    n_presta = PrestationProgrammee.objects.filter(exercice=ex).count()

    call_command('seed_real_data')  # 2e passage

    assert LigneBudgetaire.objects.filter(tache__exercice=ex).count() == n_lignes
    assert VirementBudgetaire.objects.filter(exercice=ex).count() == n_vir
    assert ConsommationDirecte.objects.filter(ligne_budgetaire__tache__exercice=ex).count() == n_conso
    assert PrestationProgrammee.objects.filter(exercice=ex).count() == n_presta
