"""Tests annotations Tache (with_aggregates) — budget porté par les lignes (refactor 0006)."""

import pytest
from decimal import Decimal
from core.models import Tache, LigneBudgetaire, VirementBudgetaire, ImputationBC
from core.tests.factories import TacheFactory, BonCommandeFactory


def _impute(tache, ligne, prestataire, exercice, montant_ttc, statut):
    """Crée un BC + son imputation sur la ligne donnée (= consommation de cette ligne)."""
    bc = BonCommandeFactory(
        tache=tache, exercice=exercice, prestataire=prestataire,
        montant_ttc=montant_ttc, statut=statut,
    )
    ImputationBC.objects.create(
        bon_commande=bc, ligne_budgetaire=ligne, montant=montant_ttc,
    )
    return bc


@pytest.mark.django_db
class TestTacheAnnotations:

    def test_with_aggregates_sans_bc(self, exercice):
        TacheFactory(exercice=exercice, numero='T-A', montant_initial=Decimal('1000000'))
        t = Tache.objects.with_aggregates().get(numero='T-A')
        assert t.budget_ajuste == Decimal('1000000')
        assert t.consommation == Decimal('0')
        assert t.solde == Decimal('1000000')

    def test_consommation_exclut_annules(self, exercice, prestataire):
        t = TacheFactory(exercice=exercice, numero='T-B', montant_initial=Decimal('1000000'))
        l1 = t.lignes.first()
        # Ligne secondaire (budget 0) pour porter le BC annulé — 1 imputation par ligne
        # afin d'éviter la double-comptabilisation du budget (produit cartésien des JOIN).
        l2 = LigneBudgetaire.objects.create(
            tache=t, code_nature='99999', libelle_nature='Annexe',
            montant_initial=Decimal('0'), actif=True,
        )
        _impute(t, l1, prestataire, exercice, Decimal('500000'), 'execute')
        _impute(t, l2, prestataire, exercice, Decimal('300000'), 'annule')
        annotated = Tache.objects.with_aggregates().get(numero='T-B')
        assert annotated.consommation == Decimal('500000')  # 300k annulé exclu
        assert annotated.solde == Decimal('500000')         # 1 000 000 - 500 000

    def test_budget_ajuste_avec_virements(self, exercice, assistante_user):
        t = TacheFactory(exercice=exercice, numero='T-C', montant_initial=Decimal('1000000'))
        autre = TacheFactory(exercice=exercice, numero='T-C2', montant_initial=Decimal('1000000'))
        ligne, ligne_autre = t.lignes.first(), autre.lignes.first()
        # +200 000 entrant puis -50 000 sortant sur la ligne de T-C → budget ajusté 1 150 000
        VirementBudgetaire.objects.create(
            exercice=exercice, ligne_source=ligne_autre, ligne_destination=ligne,
            montant=Decimal('200000'), motif='in', created_by=assistante_user,
        )
        VirementBudgetaire.objects.create(
            exercice=exercice, ligne_source=ligne, ligne_destination=ligne_autre,
            montant=Decimal('50000'), motif='out', created_by=assistante_user,
        )
        annotated = Tache.objects.with_aggregates().get(pk=t.pk)
        assert annotated.budget_ajuste == Decimal('1150000')

    def test_taux_consommation_property_utilise_cache(self, exercice, prestataire):
        t = TacheFactory(exercice=exercice, numero='T-D', montant_initial=Decimal('1000000'))
        _impute(t, t.lignes.first(), prestataire, exercice, Decimal('500000'), 'execute')
        annotated = Tache.objects.with_aggregates().get(numero='T-D')
        assert annotated.taux_consommation == Decimal('50.0')  # 500k / 1M

    def test_property_sans_annotation(self, exercice, prestataire):
        """Sans .with_aggregates() : le budget s'agrège depuis les lignes, la conso retombe à 0."""
        t = TacheFactory(exercice=exercice, numero='T-E', montant_initial=Decimal('1000000'))
        _impute(t, t.lignes.first(), prestataire, exercice, Decimal('400000'), 'execute')
        t = Tache.objects.get(numero='T-E')
        assert t.budget_initial == Decimal('1000000')
        assert t.consommation == Decimal('0')   # design actuel : pas d'annotation → 0
        assert t.solde == Decimal('1000000')

    def test_budget_non_double_multi_imputations_meme_ligne(self, exercice, prestataire):
        """Régression produit cartésien : 2 ImputationBC sur LA MÊME ligne.

        Avant le fix (Sum multi-relations dans une seule requête via JOIN), le JOIN
        lignes×imputations dupliquait la ligne → budget_initial compté 2× (2 000 000
        au lieu de 1 000 000). Le fix isole chaque agrégat dans sa propre Subquery.
        """
        t = TacheFactory(exercice=exercice, numero='T-MULTI', montant_initial=Decimal('1000000'))
        ligne = t.lignes.first()
        _impute(t, ligne, prestataire, exercice, Decimal('500000'), 'execute')
        _impute(t, ligne, prestataire, exercice, Decimal('300000'), 'execute')
        a = Tache.objects.with_aggregates().get(numero='T-MULTI')
        assert a.budget_initial == Decimal('1000000')   # PAS 2 000 000
        assert a.budget_ajuste == Decimal('1000000')    # PAS 2 000 000
        assert a.consommation == Decimal('800000')      # 500k + 300k
        assert a.solde == Decimal('200000')             # 1 000 000 - 800 000

    def test_budget_non_double_multi_virements_entrants(self, exercice, assistante_user):
        """2 virements entrants sur une même ligne ne doivent pas doubler le budget initial."""
        t = TacheFactory(exercice=exercice, numero='T-VIN', montant_initial=Decimal('1000000'))
        src = TacheFactory(exercice=exercice, numero='T-VIN2', montant_initial=Decimal('1000000'))
        dst_l, src_l = t.lignes.first(), src.lignes.first()
        for m in (Decimal('100000'), Decimal('50000')):
            VirementBudgetaire.objects.create(
                exercice=exercice, ligne_source=src_l, ligne_destination=dst_l,
                montant=m, motif='in', created_by=assistante_user,
            )
        a = Tache.objects.with_aggregates().get(numero='T-VIN')
        assert a.budget_initial == Decimal('1000000')        # PAS 2 000 000
        assert a.total_transfert_plus == Decimal('150000')   # 100k + 50k
        assert a.budget_ajuste == Decimal('1150000')


@pytest.mark.django_db
class TestLigneAnnotations:
    """LigneBudgetaireQuerySet.with_aggregates() — mêmes pièges de produit cartésien."""

    def test_ligne_multi_imputations_ne_double_pas_les_virements(
        self, exercice, prestataire, assistante_user,
    ):
        """2 imputations sur une ligne ne doivent pas doubler son virement entrant.

        Avant le fix, le JOIN imputations (2 lignes) × virements_entrants (1 ligne)
        comptait le virement 2× → transfert_plus = 400 000 au lieu de 200 000.
        """
        t = TacheFactory(exercice=exercice, numero='L-MULTI', montant_initial=Decimal('1000000'))
        ligne = t.lignes.first()
        src = LigneBudgetaire.objects.create(
            tache=t, code_nature='70000', libelle_nature='Source',
            montant_initial=Decimal('0'), actif=True,
        )
        _impute(t, ligne, prestataire, exercice, Decimal('500000'), 'execute')
        _impute(t, ligne, prestataire, exercice, Decimal('300000'), 'execute')
        VirementBudgetaire.objects.create(
            exercice=exercice, ligne_source=src, ligne_destination=ligne,
            montant=Decimal('200000'), motif='in', created_by=assistante_user,
        )
        a = LigneBudgetaire.objects.with_aggregates().get(pk=ligne.pk)
        assert a.transfert_plus == Decimal('200000')     # PAS 400 000
        assert a.consommation_bc == Decimal('800000')    # 500k + 300k
        assert a.budget_ajuste == Decimal('1200000')     # 1M + 200k
        assert a.consommation == Decimal('800000')
        assert a.solde == Decimal('400000')

    def test_ligne_conso_bc_exclut_annule(self, exercice, prestataire):
        """Sur une seule ligne : 1 BC exécuté + 1 BC annulé → seul l'exécuté compte."""
        t = TacheFactory(exercice=exercice, numero='L-ANN', montant_initial=Decimal('1000000'))
        ligne = t.lignes.first()
        _impute(t, ligne, prestataire, exercice, Decimal('500000'), 'execute')
        _impute(t, ligne, prestataire, exercice, Decimal('300000'), 'annule')
        a = LigneBudgetaire.objects.with_aggregates().get(pk=ligne.pk)
        assert a.consommation_bc == Decimal('500000')   # 300k annulé exclu
        assert a.budget_ajuste == Decimal('1000000')    # budget non doublé
        assert a.solde == Decimal('500000')
