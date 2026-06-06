"""Tests BonCommandeService - creation, transitions, atomicite."""

import pytest
from decimal import Decimal
from core.models import BonCommande, HistoriqueStatut, JournalActivite, Tache, PieceJointe
from core.services import BonCommandeService


@pytest.mark.django_db
class TestBonCommandeCreer:

    def test_creer_ok(self, tache, prestataire, dag_user, exercice):
        bc = BonCommandeService.creer(
            tache=tache, prestataire=prestataire,
            montant_ht=Decimal('1000000'), utilisateur=dag_user,
            exercice=exercice,
        )
        from datetime import date
        assert bc.pk is not None
        assert bc.numero == f"STD{date.today():%y%m}DLA00001"
        assert bc.statut == 'cree'
        assert bc.montant_ht == Decimal('1000000')
        # TVA 19.25% => TTC = 1 192 500
        assert bc.montant_ttc == Decimal('1192500.00')

    def test_numerotation_incrementale(self, tache, prestataire, dag_user, exercice):
        from datetime import date
        bc1 = BonCommandeService.creer(tache, prestataire, Decimal('500000'), dag_user, exercice)
        bc2 = BonCommandeService.creer(tache, prestataire, Decimal('500000'), dag_user, exercice)
        _p = f"STD{date.today():%y%m}DLA"
        assert bc1.numero == f"{_p}00001"
        assert bc2.numero == f"{_p}00002"

    def test_journal_create(self, tache, prestataire, dag_user, exercice):
        BonCommandeService.creer(tache, prestataire, Decimal('500000'), dag_user, exercice)
        log = JournalActivite.objects.filter(type_action='BC.create').first()
        assert log is not None
        assert log.utilisateur == dag_user

    def test_refuse_si_solde_insuffisant(self, prestataire, dag_user, exercice):
        # tache avec budget de 1M seulement
        from core.tests.factories import TacheFactory
        t = TacheFactory(exercice=exercice, montant_initial=Decimal('1000000'))
        # On essaie un BC > budget
        with pytest.raises(ValueError, match="supérieur au solde"):
            BonCommandeService.creer(t, prestataire, Decimal('2000000'), dag_user, exercice)

    def test_refuse_montant_zero(self, tache, prestataire, dag_user, exercice):
        with pytest.raises(ValueError, match="superieur a zero"):
            BonCommandeService.creer(tache, prestataire, Decimal('0'), dag_user, exercice)

    def test_refuse_sans_exercice_actif(self, tache, prestataire, dag_user):
        # tache.exercice est actif mais on ne le passe pas. Le service va le charger.
        # Pour tester un cas "pas d'exercice actif", on cloture l'exercice
        tache.exercice.statut = 'cloture'
        tache.exercice.save()
        with pytest.raises(ValueError, match="Aucun exercice"):
            BonCommandeService.creer(tache, prestataire, Decimal('100000'), dag_user)

    def test_solde_consomme_correctement(self, exercice, prestataire, dag_user):
        """Apres creation, le solde de la tache doit refleter la conso."""
        from core.tests.factories import TacheFactory
        t = TacheFactory(exercice=exercice, montant_initial=Decimal('10000000'))
        BonCommandeService.creer(t, prestataire, Decimal('1000000'), dag_user, exercice)
        # La conso/solde ne sont calculés que sur un queryset annoté (.with_aggregates()),
        # pas via refresh_from_db() (les propriétés retombent à 0 sans annotation).
        t = Tache.objects.with_aggregates().get(pk=t.pk)
        assert t.consommation == Decimal('1192500.00')
        assert t.solde == Decimal('8807500.00')


@pytest.mark.django_db
class TestBonCommandeTransitions:

    @pytest.fixture
    def bc(self, tache, prestataire, dag_user, exercice):
        bc = BonCommandeService.creer(
            tache, prestataire, Decimal('500000'), dag_user, exercice
        )
        # Pièce jointe « bon de commande signé » requise avant la notification
        PieceJointe.objects.create(
            type_entite='bc', entite_id=bc.pk, type_piece='bon_commande',
            fichier='pieces_jointes/test/bc_signe.pdf', nom_original='bc_signe.pdf',
            uploaded_by=dag_user,
        )
        return bc

    def test_transition_cree_vers_notifie(self, bc, dag_user):
        result = BonCommandeService.changer_statut(bc, 'notifie', dag_user)
        bc.refresh_from_db()
        assert bc.statut == 'notifie'
        assert bc.date_notification is not None
        assert 'notifie' in result['message']

    def test_transition_invalide_levee_value_error(self, bc, dag_user):
        # On ne peut pas passer cree -> execute directement
        with pytest.raises(ValueError, match="interdite"):
            BonCommandeService.changer_statut(bc, 'execute', dag_user)

    def test_annulation_enregistre_motif(self, bc, dag_user):
        BonCommandeService.changer_statut(bc, 'annule', dag_user, motif='Erreur saisie')
        bc.refresh_from_db()
        assert bc.statut == 'annule'
        assert bc.motif_annulation == 'Erreur saisie'

    def test_historique_cree_a_chaque_transition(self, bc, dag_user):
        BonCommandeService.changer_statut(bc, 'notifie', dag_user)
        h = HistoriqueStatut.objects.filter(type_entite='BC', entite_id=bc.id).first()
        assert h is not None
        assert h.ancien_statut == 'cree'
        assert h.nouveau_statut == 'notifie'
        assert h.utilisateur == dag_user

    def test_chemin_complet_cree_execute(self, bc, dag_user):
        BonCommandeService.changer_statut(bc, 'notifie', dag_user)
        BonCommandeService.changer_statut(bc, 'en_cours', dag_user)
        BonCommandeService.changer_statut(bc, 'execute', dag_user)
        bc.refresh_from_db()
        assert bc.statut == 'execute'


@pytest.mark.django_db
class TestCalculTVA:

    def test_calcul_montants_avec_tva(self):
        m = BonCommandeService.calculer_montants_avec_tva(Decimal('1000000'))
        assert m['montant_ht'] == Decimal('1000000')
        assert m['montant_tva'] == Decimal('192500.00')
        assert m['montant_ttc'] == Decimal('1192500.00')

    def test_taux_tva_personnalise(self):
        m = BonCommandeService.calculer_montants_avec_tva(
            Decimal('1000'), taux_tva=Decimal('10')
        )
        assert m['montant_tva'] == Decimal('100.00')
        assert m['montant_ttc'] == Decimal('1100.00')
