# -*- coding: utf-8 -*-
"""
Audit d'integrite complet de BudgetPAD.
Usage : python manage.py audit_integrite
"""
from django.core.management.base import BaseCommand
from django.db.models import Count, F, Q, Sum
from decimal import Decimal


class Command(BaseCommand):
    help = "Audit complet de l'integrite des donnees BudgetPAD"

    def handle(self, *args, **options):
        from core.models import (
            ExerciceBudgetaire, Tache, LigneBudgetaire, DemandeAchat,
            BonCommande, ImputationBC, VirementBudgetaire, Utilisateur,
        )

        ok = self.style.SUCCESS
        err = self.style.ERROR
        warn = self.style.WARNING
        total_ok = total_err = total_warn = 0

        def check(label, passed, detail='', is_warning=False):
            nonlocal total_ok, total_err, total_warn
            if passed:
                self.stdout.write(ok(f'  [OK] {label}'))
                total_ok += 1
            elif is_warning:
                self.stdout.write(warn(f'  [!!] {label}' + (f' - {detail}' if detail else '')))
                total_warn += 1
            else:
                self.stdout.write(err(f'  [KO] {label}' + (f' - {detail}' if detail else '')))
                total_err += 1

        self.stdout.write('\n' + '='*55)
        self.stdout.write("  AUDIT D'INTEGRITE - BUDGETPAD")
        self.stdout.write('='*55 + '\n')

        # ── A. Exercices ──────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('A. Exercices'))
        actifs = ExerciceBudgetaire.objects.filter(statut='actif').count()
        check('Un seul exercice actif', actifs == 1,
              f'{actifs} exercice(s) actif(s) trouve(s)')

        clotures_non_lock = ExerciceBudgetaire.objects.filter(
            statut='cloture', is_locked=False
        ).count()
        check('Exercices clotures ont is_locked=True', clotures_non_lock == 0,
              f'{clotures_non_lock} exercice(s) cloture(s) sans is_locked', is_warning=True)

        dates_invalides = ExerciceBudgetaire.objects.filter(
            date_fin__lte=F('date_debut')
        ).count()
        check('Dates exercices coherentes (debut < fin)', dates_invalides == 0,
              f'{dates_invalides} exercice(s) avec dates incoherentes')

        # ── B. Taches et lignes ───────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('B. Taches et lignes'))
        lignes_neg = LigneBudgetaire.objects.filter(montant_initial__lt=0).count()
        check('Aucune ligne budgetaire a montant negatif', lignes_neg == 0,
              f'{lignes_neg} ligne(s) avec montant_initial < 0')

        # ── C. Demandes d'achat ───────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING("C. Demandes d'achat"))
        das_validees_sans_offre = DemandeAchat.objects.filter(
            statut='validee'
        ).annotate(
            nb_retenues=Count('offres', filter=Q(offres__statut='retenue'))
        ).filter(nb_retenues=0).count()
        check('Toutes les DA validees ont 1 offre retenue',
              das_validees_sans_offre == 0,
              f'{das_validees_sans_offre} DA validee(s) sans offre retenue')

        das_validees_multi = DemandeAchat.objects.filter(
            statut='validee'
        ).annotate(
            nb_retenues=Count('offres', filter=Q(offres__statut='retenue'))
        ).filter(nb_retenues__gt=1).count()
        check("Aucune DA avec plus d'une offre retenue",
              das_validees_multi == 0,
              f'{das_validees_multi} DA avec plusieurs offres retenues')

        # ── D. Bons de commande ───────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('D. Bons de commande'))

        bcs_sans_imputation = BonCommande.objects.exclude(
            statut='annule'
        ).annotate(nb_imp=Count('imputations')).filter(nb_imp=0).count()
        check('Tous les BC actifs ont au moins 1 imputation',
              bcs_sans_imputation == 0,
              f'{bcs_sans_imputation} BC non annule(s) sans imputation', is_warning=True)

        bcs_sans_echeance = BonCommande.objects.filter(
            statut__in=['notifie', 'en_cours'],
            date_echeance__isnull=True
        ).count()
        check("Tous les BC notifies/en_cours ont une date d'echeance",
              bcs_sans_echeance == 0,
              f'{bcs_sans_echeance} BC notifie(s)/en cours sans echeance', is_warning=True)

        # ── E. Imputations ────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('E. Imputations'))

        imp_sur_lock = ImputationBC.objects.filter(
            bon_commande__exercice__is_locked=True
        ).exclude(bon_commande__statut='annule').count()
        check('Aucune imputation active sur exercice verrouille',
              imp_sur_lock == 0,
              f'{imp_sur_lock} imputation(s) sur exercice verrouille', is_warning=True)

        incoherents = 0
        for bc in BonCommande.objects.exclude(statut='annule').annotate(
            total_imp=Sum('imputations__montant')
        ):
            total = bc.total_imp or Decimal('0')
            if abs(total - bc.montant_ttc) > Decimal('1'):
                incoherents += 1
        check('Somme imputations = montant TTC pour chaque BC',
              incoherents == 0,
              f'{incoherents} BC avec imputations != TTC')

        # ── F. Virements ──────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('F. Virements'))
        virements_meme_ligne = VirementBudgetaire.objects.filter(
            ligne_source=F('ligne_destination')
        ).count()
        check('Aucun virement source = destination',
              virements_meme_ligne == 0,
              f'{virements_meme_ligne} virement(s) avec source = destination')

        # ── G. Utilisateurs ───────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING('G. Utilisateurs'))
        admins = Utilisateur.objects.filter(role='admin', is_active=True).count()
        check('Au moins 1 administrateur actif', admins >= 1,
              f'{admins} admin(s) actif(s) trouve(s)')

        users_sans_role = Utilisateur.objects.filter(role='').count()
        check('Tous les utilisateurs ont un role defini', users_sans_role == 0,
              f'{users_sans_role} utilisateur(s) sans role')

        # ── Resume ────────────────────────────────────────────────
        self.stdout.write('\n' + '='*55)
        self.stdout.write(ok(f'  [OK] Reussi   : {total_ok}'))
        if total_warn:
            self.stdout.write(warn(f'  [!!] Alertes  : {total_warn}'))
        if total_err:
            self.stdout.write(err(f'  [KO] Erreurs  : {total_err}'))
        self.stdout.write('='*55)

        if total_err == 0 and total_warn == 0:
            self.stdout.write(ok('\n  Integrite parfaite - pret pour la production.\n'))
        elif total_err == 0:
            self.stdout.write(warn('\n  Quelques alertes a examiner avant la mise en production.\n'))
        else:
            self.stdout.write(err('\n  Des erreurs critiques doivent etre corrigees.\n'))
