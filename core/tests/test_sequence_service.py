"""Tests SequenceService - numerotation atomique."""

import pytest
from core.models import Sequence
from core.services import SequenceService


@pytest.mark.django_db
class TestSequenceService:

    def test_next_value_initial(self):
        """Premiere valeur d'un compteur inconnu = 1."""
        assert SequenceService.next_value('FOO') == 1

    def test_next_value_monotone(self):
        """Les appels successifs incrementent strictement."""
        for expected in range(1, 11):
            assert SequenceService.next_value('BAR') == expected

    def test_independent_keys(self):
        """Deux cles distinctes ont des compteurs independants."""
        SequenceService.next_value('A')
        SequenceService.next_value('A')
        assert SequenceService.next_value('B') == 1

    def test_bc_numero_format(self):
        from datetime import date
        yymm = date.today().strftime('%y%m')
        assert SequenceService.next_bc_numero() == f'STD{yymm}DLA00001'
        assert SequenceService.next_bc_numero() == f'STD{yymm}DLA00002'

    def test_da_reference_format(self):
        from datetime import date
        yymm = date.today().strftime('%y%m')
        assert SequenceService.next_da_reference() == f'DAC{yymm}DLA00001'

    def test_prestataire_code_format(self):
        assert SequenceService.next_prestataire_code() == 'PREST-001'

    def test_tache_numero_format(self):
        assert SequenceService.next_tache_numero(2025) == 'T-001'

    def test_persistance_db(self):
        """La valeur est bien persistee dans la table Sequence."""
        SequenceService.next_value('CHECK')
        SequenceService.next_value('CHECK')
        SequenceService.next_value('CHECK')
        assert Sequence.objects.get(key='CHECK').value == 3
