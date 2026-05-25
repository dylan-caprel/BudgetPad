"""Tests annotations Tache (with_aggregates)."""

import pytest
from decimal import Decimal
from core.models import Tache
from core.tests.factories import TacheFactory, BonCommandeFactory


@pytest.mark.django_db
class TestTacheAnnotations:

    def test_with_aggregates_sans_bc(self, exercice):
        TacheFactory(exercice=exercice, numero='T-A', montant_initial=Decimal('1000000'))
        t = Tache.objects.with_aggregates().get(numero='T-A')
        assert t._budget_ajuste == Decimal('1000000')
        assert t._consommation == Decimal('0')
        assert t._solde == Decimal('1000000')

    def test_consommation_exclut_annules(self, exercice, prestataire):
        t = TacheFactory(exercice=exercice, numero='T-B', montant_initial=Decimal('1000000'))
        BonCommandeFactory(tache=t, exercice=exercice, prestataire=prestataire,
                           montant_ttc=Decimal('500000'), statut='execute')
        BonCommandeFactory(tache=t, exercice=exercice, prestataire=prestataire,
                           montant_ttc=Decimal('300000'), statut='annule')
        annotated = Tache.objects.with_aggregates().get(numero='T-B')
        assert annotated._consommation == Decimal('500000')  # 300k annule exclu
        assert annotated._solde == Decimal('500000')

    def test_budget_ajuste_avec_transactions(self, exercice):
        t = TacheFactory(
            exercice=exercice, numero='T-C',
            montant_initial=Decimal('1000000'),
            transactions_plus=Decimal('200000'),
            transactions_moins=Decimal('50000'),
        )
        annotated = Tache.objects.with_aggregates().get(pk=t.pk)
        assert annotated._budget_ajuste == Decimal('1150000')

    def test_taux_consommation_property_utilise_cache(self, exercice, prestataire):
        t = TacheFactory(exercice=exercice, numero='T-D', montant_initial=Decimal('1000000'))
        BonCommandeFactory(tache=t, exercice=exercice, prestataire=prestataire,
                           montant_ttc=Decimal('500000'), statut='execute')
        annotated = Tache.objects.with_aggregates().get(numero='T-D')
        # 500k / 1M = 50%
        assert annotated.taux_consommation == Decimal('50.0')

    def test_property_fonctionne_sans_annotation(self, exercice, prestataire):
        """Si l'objet n'est pas annote, les properties retombent sur l'agregation Python."""
        t = TacheFactory(exercice=exercice, numero='T-E', montant_initial=Decimal('1000000'))
        BonCommandeFactory(tache=t, exercice=exercice, prestataire=prestataire,
                           montant_ttc=Decimal('400000'), statut='execute')
        # Recharger sans .with_aggregates()
        t = Tache.objects.get(numero='T-E')
        assert t.consommation == Decimal('400000')
        assert t.solde == Decimal('600000')
