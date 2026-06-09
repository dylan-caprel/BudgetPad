"""Tests du CRUD admin des prestations du journal de programmation."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import ExerciceBudgetaire, PrestationProgrammee


@pytest.fixture
def exercice_actif(db):
    return ExerciceBudgetaire.objects.create(
        annee=2026, date_debut=date(2026, 1, 1), date_fin=date(2026, 12, 31),
        montant_global=0, statut='actif', is_active=True,
    )


@pytest.mark.django_db
def test_admin_cree_prestation_avec_parsing_fr(client, admin_user, exercice_actif):
    client.force_login(admin_user)
    resp = client.post(reverse('prestation_create'), {
        'code_tache': '3211038', 'libelle_tache': 'ANALYSE RISQUES',
        'code_nature': '6324130', 'libelle_nature': 'HONORAIRES',
        'objet_prestation': 'Étude de conformité', 'nature_prestation': 'PRESTATION_INT',
        'montant_ht': '1 500 000,50', 'budget_previsionnel': '2000000',
        'periode': 'quad', 'priorite': '1', 'statut': 'programmee',
    })
    assert resp.status_code == 302
    p = PrestationProgrammee.objects.get(exercice=exercice_actif)
    assert p.objet_prestation == 'Étude de conformité'
    assert p.montant_ht == Decimal('1500000.50')   # format FR toléré
    assert p.nature_prestation == 'PRESTATION_INT'
    assert p.numero_ligne == 1


@pytest.mark.django_db
def test_admin_modifie_et_supprime(client, admin_user, exercice_actif):
    client.force_login(admin_user)
    p = PrestationProgrammee.objects.create(
        exercice=exercice_actif, numero_ligne=1, code_tache='X', code_nature='Y',
        objet_prestation='Avant', nature_prestation='APPRO', montant_ht=Decimal('100'),
        periode='quad', priorite='1', statut='programmee',
    )
    resp = client.post(reverse('prestation_edit', args=[p.pk]), {
        'code_tache': 'X', 'code_nature': 'Y', 'libelle_tache': '', 'libelle_nature': '',
        'objet_prestation': 'Après', 'nature_prestation': 'TRAVAUX', 'montant_ht': '250',
        'budget_previsionnel': '', 'periode': 'penta', 'priorite': '2', 'statut': 'en_cours',
    })
    assert resp.status_code == 302
    p.refresh_from_db()
    assert p.objet_prestation == 'Après'
    assert p.nature_prestation == 'TRAVAUX'
    assert p.statut == 'en_cours'
    assert p.periode == 'penta'

    resp = client.post(reverse('prestation_delete', args=[p.pk]))
    assert resp.status_code == 302
    assert not PrestationProgrammee.objects.filter(pk=p.pk).exists()


@pytest.mark.django_db
def test_create_lie_la_ligne_budgetaire(client, admin_user, exercice_actif, django_user_model):
    """Si la ligne (tâche+nature) existe, la prestation s'y rattache automatiquement."""
    from core.models import Tache, LigneBudgetaire
    t = Tache.objects.create(exercice=exercice_actif, numero='3211038', titre='ANALYSE', actif=True)
    ligne = LigneBudgetaire.objects.create(tache=t, code_nature='6324130',
                                           libelle_nature='HONORAIRES', montant_initial=Decimal('5000000'))
    client.force_login(admin_user)
    client.post(reverse('prestation_create'), {
        'code_tache': '3211038', 'code_nature': '6324130', 'libelle_tache': '', 'libelle_nature': '',
        'objet_prestation': 'Test lien', 'nature_prestation': 'APPRO', 'montant_ht': '100000',
        'budget_previsionnel': '', 'periode': 'quad', 'priorite': '1', 'statut': 'programmee',
    })
    p = PrestationProgrammee.objects.get(objet_prestation='Test lien')
    assert p.ligne_budgetaire_id == ligne.id


@pytest.mark.django_db
def test_non_admin_refuse(client, assistante_user, exercice_actif):
    client.force_login(assistante_user)
    client.post(reverse('prestation_create'), {
        'objet_prestation': 'Interdit', 'montant_ht': '100', 'nature_prestation': 'APPRO',
        'periode': 'quad', 'priorite': '1', 'statut': 'programmee',
    })
    assert PrestationProgrammee.objects.count() == 0


@pytest.mark.django_db
def test_objet_obligatoire(client, admin_user, exercice_actif):
    client.force_login(admin_user)
    client.post(reverse('prestation_create'), {
        'objet_prestation': '', 'montant_ht': '100', 'nature_prestation': 'APPRO',
        'periode': 'quad', 'priorite': '1', 'statut': 'programmee',
    })
    assert PrestationProgrammee.objects.count() == 0   # rejeté (objet vide)
