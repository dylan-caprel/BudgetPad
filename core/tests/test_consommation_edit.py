"""Tests du module Consommations directes : rendu, édition admin, sécurité, solde."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import (
    Utilisateur, ExerciceBudgetaire, Tache, LigneBudgetaire, ConsommationDirecte,
)


def _setup():
    ex = ExerciceBudgetaire.objects.create(
        annee=2099, date_debut=date(2099, 1, 1), date_fin=date(2099, 12, 31),
        montant_global=Decimal('0'), statut='actif', is_active=True,
    )
    t = Tache.objects.create(exercice=ex, numero='T1', titre='Tache test', actif=True)
    l = LigneBudgetaire.objects.create(
        tache=t, code_nature='6047210', libelle_nature='FOURNITURES',
        montant_initial=Decimal('1000000'),
    )
    c = ConsommationDirecte.objects.create(
        ligne_budgetaire=l, montant=Decimal('200000'), motif='achat_direct',
        description='', date_consommation=date(2099, 1, 2),
    )
    return ex, t, l, c


def _user(role):
    return Utilisateur.objects.create_user(
        username=f'u_{role}', password='x', role=role,
        nom_complet=role.title(), must_change_password=False,
    )


@pytest.mark.django_db
def test_liste_consommations_rend(client):
    _setup()
    client.force_login(_user('admin'))
    r = client.get(reverse('consommations_list'))
    assert r.status_code == 200
    assert 'Consommations directes' in r.content.decode()


@pytest.mark.django_db
def test_admin_peut_editer(client):
    _, _, _, c = _setup()
    client.force_login(_user('admin'))
    r = client.post(reverse('consommation_edit', args=[c.pk]), {
        'montant': '300000', 'motif': 'achat_direct', 'description': 'maj',
        'date_consommation': '2099-01-03', 'numero_capri': 'CAPRI-9', 'date_capri': '2099-01-03',
    })
    assert r.status_code == 302
    c.refresh_from_db()
    assert c.montant == Decimal('300000')
    assert c.numero_capri == 'CAPRI-9'
    assert c.description == 'maj'


@pytest.mark.django_db
def test_non_admin_ne_peut_pas_editer(client):
    _, _, _, c = _setup()
    client.force_login(_user('lecteur'))
    client.post(reverse('consommation_edit', args=[c.pk]), {
        'montant': '300000', 'motif': 'achat_direct', 'description': 'hack',
        'date_consommation': '2099-01-03', 'numero_capri': 'X', 'date_capri': '2099-01-03',
    })
    c.refresh_from_db()
    assert c.montant == Decimal('200000')  # inchangé
    assert c.description == ''


@pytest.mark.django_db
def test_edit_respecte_le_solde(client):
    # ligne 1 000 000, conso 200 000 -> disponible pour cette conso = 800 000 + 200 000 = 1 000 000
    _, _, _, c = _setup()
    client.force_login(_user('admin'))
    # 1 200 000 > 1 000 000 -> refusé
    client.post(reverse('consommation_edit', args=[c.pk]), {
        'montant': '1200000', 'motif': 'achat_direct', 'description': '',
        'date_consommation': '2099-01-03', 'numero_capri': 'C', 'date_capri': '2099-01-03',
    })
    c.refresh_from_db()
    assert c.montant == Decimal('200000')  # refusé
    # 1 000 000 == disponible -> accepté
    client.post(reverse('consommation_edit', args=[c.pk]), {
        'montant': '1000000', 'motif': 'achat_direct', 'description': '',
        'date_consommation': '2099-01-03', 'numero_capri': 'C', 'date_capri': '2099-01-03',
    })
    c.refresh_from_db()
    assert c.montant == Decimal('1000000')  # accepté


@pytest.mark.django_db
def test_consommation_annulee_non_editable(client):
    _, _, _, c = _setup()
    c.est_annule = True
    c.save(update_fields=['est_annule'])
    client.force_login(_user('admin'))
    client.post(reverse('consommation_edit', args=[c.pk]), {
        'montant': '500000', 'motif': 'achat_direct', 'description': 'x',
        'date_consommation': '2099-01-03', 'numero_capri': 'C', 'date_capri': '2099-01-03',
    })
    c.refresh_from_db()
    assert c.montant == Decimal('200000')  # inchangé (annulée)
