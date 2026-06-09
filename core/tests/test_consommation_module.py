"""Tests du module dédié Consommations directes (liste, création, annulation)."""
from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from core.models import ConsommationDirecte


@pytest.fixture
def ligne_active(ligne_budgetaire):
    """Ligne budgétaire (10 000 000) sur un exercice rendu actif."""
    ex = ligne_budgetaire.tache.exercice
    ex.is_active = True
    ex.statut = 'actif'
    ex.save()
    return ligne_budgetaire


def _payload(ligne, montant='5000000'):
    return {
        'ligne_budgetaire': ligne.pk,
        'montant': montant,
        'motif': 'achat_direct',
        'description': 'Test conso module',
        'date_consommation': '2025-06-01',
        'numero_capri': 'CAPRI-2025-0001',
        'date_capri': '2025-05-20',
    }


@pytest.mark.django_db
def test_liste_module_rend(client, admin_user, ligne_active):
    client.force_login(admin_user)
    resp = client.get(reverse('consommations_list'))
    assert resp.status_code == 200


@pytest.mark.django_db
def test_assistante_cree_consommation(client, assistante_user, ligne_active):
    client.force_login(assistante_user)
    resp = client.post(reverse('consommation_create_module'), _payload(ligne_active, '5000000'))
    assert resp.status_code == 302
    c = ConsommationDirecte.objects.get(ligne_budgetaire=ligne_active)
    assert c.montant == Decimal('5000000')
    assert c.numero_capri == 'CAPRI-2025-0001'
    assert c.est_annule is False


@pytest.mark.django_db
def test_solde_insuffisant_refuse(client, assistante_user, ligne_active):
    client.force_login(assistante_user)
    # 20M demandés sur une ligne de 10M -> refusé
    client.post(reverse('consommation_create_module'), _payload(ligne_active, '20000000'))
    assert ConsommationDirecte.objects.count() == 0


@pytest.mark.django_db
def test_capri_obligatoire(client, assistante_user, ligne_active):
    client.force_login(assistante_user)
    data = _payload(ligne_active)
    data['numero_capri'] = ''
    data['date_capri'] = ''
    client.post(reverse('consommation_create_module'), data)
    assert ConsommationDirecte.objects.count() == 0   # R11 : CAPRI requis


@pytest.mark.django_db
def test_role_non_autorise_refuse(client, dag_user, ligne_active):
    client.force_login(dag_user)   # rôle 'dag' non autorisé pour la création
    client.post(reverse('consommation_create_module'), _payload(ligne_active))
    assert ConsommationDirecte.objects.count() == 0


@pytest.mark.django_db
def test_annulation_depuis_module(client, admin_user, ligne_active):
    c = ConsommationDirecte.objects.create(
        ligne_budgetaire=ligne_active, montant=Decimal('1000000'), motif='achat_direct',
        date_consommation=date(2025, 6, 1), numero_capri='CAPRI-X', date_capri=date(2025, 5, 1),
        created_by=admin_user,
    )
    client.force_login(admin_user)
    resp = client.post(reverse('annuler_consommation_directe', args=[c.pk]),
                       {'motif': 'Erreur de saisie corrigée', 'next': 'consommations_list'})
    assert resp.status_code == 302
    assert resp.url == reverse('consommations_list')   # retour au module
    c.refresh_from_db()
    assert c.est_annule is True
