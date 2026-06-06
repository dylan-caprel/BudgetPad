"""Fixtures pytest globales."""

import pytest
from decimal import Decimal
from .factories import (
    UtilisateurFactory, ExerciceBudgetaireFactory, TacheFactory,
    PrestataireFactory,
)


@pytest.fixture
def exercice(db):
    return ExerciceBudgetaireFactory(annee=2025)


@pytest.fixture
def admin_user(db):
    return UtilisateurFactory(username='admin_test', role='admin')


@pytest.fixture
def dag_user(db):
    return UtilisateurFactory(username='dag_test', role='dag')


@pytest.fixture
def assistante_user(db):
    return UtilisateurFactory(username='assistante_test', role='assistante_drh')


@pytest.fixture
def tache(exercice):
    # TacheFactory crée automatiquement une ligne budgétaire active de ce montant.
    return TacheFactory(
        exercice=exercice,
        numero='T-001',
        montant_initial=Decimal('10000000'),
    )


@pytest.fixture
def ligne_budgetaire(tache):
    """Ligne budgétaire active portée par la tâche (budget 10 000 000)."""
    return tache.lignes.first()


@pytest.fixture
def prestataire(db):
    return PrestataireFactory(nom='Acme SARL')
