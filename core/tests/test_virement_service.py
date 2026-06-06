"""Tests VirementService - virements entre lignes budgétaires (refactor 0006)."""

import pytest
from decimal import Decimal
from core.models import JournalActivite, Tache
from core.services import VirementService
from core.tests.factories import TacheFactory


@pytest.mark.django_db
class TestVirementService:

    def test_virement_ok(self, exercice, assistante_user):
        src = TacheFactory(exercice=exercice, montant_initial=Decimal('5000000'))
        dst = TacheFactory(exercice=exercice, montant_initial=Decimal('1000000'))
        ls, ld = src.lignes.first(), dst.lignes.first()
        v = VirementService.creer_virement(
            ligne_source=ls, ligne_destination=ld,
            montant=Decimal('1000000'), motif="Test",
            utilisateur=assistante_user, exercice=exercice,
        )
        assert v.pk is not None
        src_a = Tache.objects.with_aggregates().get(pk=src.pk)
        dst_a = Tache.objects.with_aggregates().get(pk=dst.pk)
        # Le transfert se reflète dans le budget ajusté des deux tâches
        assert src_a.total_transfert_moins == Decimal('1000000')
        assert dst_a.total_transfert_plus == Decimal('1000000')
        assert src_a.budget_ajuste == Decimal('4000000')
        assert dst_a.budget_ajuste == Decimal('2000000')

    def test_refuse_source_egale_dest(self, exercice, assistante_user):
        ligne = TacheFactory(exercice=exercice).lignes.first()
        with pytest.raises(ValueError, match="diff"):
            VirementService.creer_virement(ligne, ligne, Decimal('1000'), "x", assistante_user)

    def test_refuse_montant_negatif(self, exercice, assistante_user):
        s = TacheFactory(exercice=exercice).lignes.first()
        d = TacheFactory(exercice=exercice).lignes.first()
        with pytest.raises(ValueError, match="positif"):
            VirementService.creer_virement(s, d, Decimal('-1000'), "x", assistante_user)

    def test_refuse_solde_insuffisant(self, exercice, assistante_user):
        s = TacheFactory(exercice=exercice, montant_initial=Decimal('100')).lignes.first()
        d = TacheFactory(exercice=exercice).lignes.first()
        with pytest.raises(ValueError, match="insuffisant"):
            VirementService.creer_virement(s, d, Decimal('1000000'), "x", assistante_user)

    def test_journal_create(self, exercice, assistante_user):
        s = TacheFactory(exercice=exercice, montant_initial=Decimal('5000000')).lignes.first()
        d = TacheFactory(exercice=exercice).lignes.first()
        VirementService.creer_virement(s, d, Decimal('100000'), "x", assistante_user)
        assert JournalActivite.objects.filter(type_action='Virement').count() == 1
