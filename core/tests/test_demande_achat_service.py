"""Tests DemandeAchatService (DA liée à une ligne budgétaire)."""

import pytest
from datetime import date
from decimal import Decimal
from core.models import DemandeAchat, JournalActivite, Notification
from core.services import DemandeAchatService


def _ref(i):
    """Référence attendue au format réel PAD : DAC{AAMM}DLA{NNNNN}."""
    return f"DAC{date.today():%y%m}DLA{i:05d}"


@pytest.mark.django_db
class TestDemandeAchatCreer:

    def test_creer_ok(self, ligne_budgetaire, assistante_user, exercice):
        da = DemandeAchatService.creer(
            ligne_budgetaire=ligne_budgetaire, objet="Achat fournitures",
            montant_estime=Decimal('500000'),
            utilisateur=assistante_user, exercice=exercice,
        )
        assert da.reference == _ref(1)
        assert da.statut == 'cree'  # PAS 'creee' - bug Sprint 0 verifie
        assert da.created_by == assistante_user

    def test_journal_create(self, ligne_budgetaire, assistante_user, exercice):
        DemandeAchatService.creer(
            ligne_budgetaire, "test", Decimal('100000'), assistante_user, exercice=exercice
        )
        assert JournalActivite.objects.filter(type_action='DA.create').count() == 1

    def test_notifie_validateurs(self, ligne_budgetaire, assistante_user, admin_user, exercice):
        """L'admin reçoit une notification 'à valider' (rôles notifiés : directeur_drh + admin)."""
        DemandeAchatService.creer(
            ligne_budgetaire, "test", Decimal('100000'), assistante_user, exercice=exercice
        )
        notifs_admin = Notification.objects.filter(utilisateur=admin_user, type='da_a_valider')
        assert notifs_admin.count() == 1

    def test_refuse_montant_negatif(self, ligne_budgetaire, assistante_user, exercice):
        with pytest.raises(ValueError, match="supérieur à zéro"):
            DemandeAchatService.creer(
                ligne_budgetaire, "test", Decimal('-100'), assistante_user, exercice=exercice
            )

    def test_numerotation_atomique(self, ligne_budgetaire, assistante_user, exercice):
        for i in range(1, 4):
            da = DemandeAchatService.creer(
                ligne_budgetaire, f"DA {i}", Decimal('100000'), assistante_user, exercice=exercice
            )
            assert da.reference == _ref(i)
