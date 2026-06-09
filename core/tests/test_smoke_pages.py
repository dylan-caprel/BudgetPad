"""Smoke tests : les pages de saisie manuelle s'affichent sans erreur (HTTP 200).

Garantit que les listes/formulaires que l'équipe remplira manuellement
(DA, BC, virements, tâches, consommation, journal) sont fonctionnels.
"""
import pytest
from django.urls import reverse


@pytest.fixture
def exercice_actif_avec_ligne(db, ligne_budgetaire):
    ex = ligne_budgetaire.tache.exercice
    ex.is_active = True
    ex.statut = 'actif'
    ex.save()
    return ex, ligne_budgetaire


@pytest.mark.django_db
def test_pages_listes_et_saisie(client, admin_user, exercice_actif_avec_ligne, prestataire):
    """Les pages-listes (qui portent les formulaires/modales de saisie manuelle) s'affichent."""
    client.force_login(admin_user)
    for name in [
        'dashboard', 'da_list', 'bc_list', 'taches_list', 'virements_list',
        'prestataires_list', 'bilans', 'exercices_list', 'journal_list',
    ]:
        resp = client.get(reverse(name))
        assert resp.status_code == 200, f"{name} -> HTTP {resp.status_code}"


@pytest.mark.django_db
def test_pages_avec_ligne(client, admin_user, exercice_actif_avec_ligne):
    _, ligne = exercice_actif_avec_ligne
    client.force_login(admin_user)
    resp = client.get(reverse('consommation_create', args=[ligne.pk]))
    assert resp.status_code == 200
    resp = client.get(reverse('ligne_detail', args=[ligne.pk]))
    assert resp.status_code == 200
