"""Tests VirementService - atomicite et validations."""

import pytest
from decimal import Decimal
from core.models import VirementBudgetaire, JournalActivite
from core.services import VirementService
from core.tests.factories import TacheFactory


@pytest.mark.django_db
class TestVirementService:

    def test_virement_ok(self, exercice, assistante_user):
        src = TacheFactory(exercice=exercice, montant_initial=Decimal('5000000'))
        dst = TacheFactory(exercice=exercice, montant_initial=Decimal('1000000'))
        v = VirementService.creer_virement(
            tache_source=src, tache_dest=dst,
            montant=Decimal('1000000'), motif="Test",
            utilisateur=assistante_user,
        )
        assert v.pk is not None
        src.refresh_from_db()
        dst.refresh_from_db()
        assert src.transactions_moins == Decimal('1000000')
        assert dst.transactions_plus == Decimal('1000000')

    def test_refuse_source_egale_dest(self, exercice, assistante_user):
        t = TacheFactory(exercice=exercice)
        with pytest.raises(ValueError, match="diff"):
            VirementService.creer_virement(t, t, Decimal('1000'), "x", assistante_user)

    def test_refuse_montant_negatif(self, exercice, assistante_user):
        s = TacheFactory(exercice=exercice)
        d = TacheFactory(exercice=exercice)
        with pytest.raises(ValueError, match="positif"):
            VirementService.creer_virement(s, d, Decimal('-1000'), "x", assistante_user)

    def test_refuse_solde_insuffisant(self, exercice, assistante_user):
        s = TacheFactory(exercice=exercice, montant_initial=Decimal('100'))
        d = TacheFactory(exercice=exercice)
        with pytest.raises(ValueError, match="insuffisant"):
            VirementService.creer_virement(s, d, Decimal('1000000'), "x", assistante_user)

    def test_journal_create(self, exercice, assistante_user):
        s = TacheFactory(exercice=exercice, montant_initial=Decimal('5000000'))
        d = TacheFactory(exercice=exercice)
        VirementService.creer_virement(s, d, Decimal('100000'), "x", assistante_user)
        assert JournalActivite.objects.filter(type_action='Virement').count() == 1
