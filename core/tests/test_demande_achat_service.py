"""Tests DemandeAchatService."""

import pytest
from decimal import Decimal
from core.models import DemandeAchat, JournalActivite, Notification
from core.services import DemandeAchatService


@pytest.mark.django_db
class TestDemandeAchatCreer:

    def test_creer_ok(self, tache, assistante_user, exercice):
        da = DemandeAchatService.creer(
            tache=tache, objet="Achat fournitures",
            montant_estime=Decimal('500000'),
            utilisateur=assistante_user, exercice=exercice,
        )
        assert da.reference == 'DA-2025-001'
        assert da.statut == 'cree'  # PAS 'creee' - bug Sprint 0 verifie
        assert da.created_by == assistante_user

    def test_journal_create(self, tache, assistante_user, exercice):
        DemandeAchatService.creer(
            tache, "test", Decimal('100000'), assistante_user, exercice
        )
        assert JournalActivite.objects.filter(type_action='DA.create').count() == 1

    def test_notifie_validateurs(self, tache, assistante_user, dag_user, admin_user, exercice):
        """Le DAG et l'admin recoivent une notification 'a valider'."""
        DemandeAchatService.creer(
            tache, "test", Decimal('100000'), assistante_user, exercice
        )
        notifs_dag = Notification.objects.filter(utilisateur=dag_user, type='da_a_valider')
        notifs_admin = Notification.objects.filter(utilisateur=admin_user, type='da_a_valider')
        assert notifs_dag.count() == 1
        assert notifs_admin.count() == 1

    def test_refuse_montant_negatif(self, tache, assistante_user, exercice):
        with pytest.raises(ValueError, match="superieur a zero"):
            DemandeAchatService.creer(
                tache, "test", Decimal('-100'), assistante_user, exercice
            )

    def test_numerotation_atomique(self, tache, assistante_user, exercice):
        for i in range(1, 4):
            da = DemandeAchatService.creer(
                tache, f"DA {i}", Decimal('100000'), assistante_user, exercice
            )
            assert da.reference == f'DA-2025-{i:03d}'
