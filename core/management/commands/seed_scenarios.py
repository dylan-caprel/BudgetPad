"""
Génère des scénarios de démo réalistes pour BudgetPAD.
À exécuter APRÈS `seed_real_data` (qui crée les 49 tâches officielles).

    python manage.py seed_scenarios
    python manage.py seed_scenarios --reset   # supprime d'abord les démos existantes

Ce script crée :
  - 15 prestataires fictifs (réalistes pour Douala)
  - 20 demandes d'achat à différents stades (créée, en étude, validée, refusée, BC créé)
  - ~35 offres prestataires (en attente, reçues, retenues, refusées)
  - 12 bons de commande (1 créé, 2 notifiés, 2 en cours, 5 exécutés, 2 annulés)
  - 3 virements budgétaires (dont 2 issus du PDF officiel)
  - 1 prolongation de BC
  - Des entrées de journal et alertes pour donner vie au dashboard
"""
from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from core.models import (
    Utilisateur, ExerciceBudgetaire, Tache, LigneBudgetaire,
    VirementBudgetaire, Prestataire, DemandeAchat, Offre, BonCommande,
    LigneBC, ImputationBC, ProlongationBC, JournalActivite, Notification,
    Alerte, HistoriqueStatut,
)


PRESTATAIRES = [
    ("PREST-001", "SARL Papeterie Centrale", "Rue Joss, Douala", "233 699 123 456", "contact@papeterie-centrale.cm"),
    ("PREST-002", "ETS Informatique Plus", "Bd de la Liberté, Douala", "233 677 234 567", "info@infoplus.cm"),
    ("PREST-003", "Imprimerie Moderne du Littoral", "Akwa, Douala", "233 655 345 678", "imprimerie.moderne@gmail.com"),
    ("PREST-004", "SARL MédiPharm Douala", "Bonanjo, Douala", "233 699 456 789", "medipharm@yahoo.fr"),
    ("PREST-005", "Cabinet Conseil RH Afrique", "Bonapriso, Douala", "233 677 567 890", "cabinet.rh@gmail.com"),
    ("PREST-006", "Transport Express Cameroun", "Zone Portuaire, Douala", "233 655 678 901", "transport.express@cm.com"),
    ("PREST-007", "Traiteur Le Festin", "Akwa, Douala", "233 699 789 012", "lefestin@gmail.com"),
    ("PREST-008", "Clinique Bonanjo Santé", "Bonanjo, Douala", "233 677 890 123", "clinique.bonanjo@yahoo.fr"),
    ("PREST-009", "Digital Solutions Cameroun", "Bonapriso, Douala", "233 655 901 234", "digital.solutions@gmail.com"),
    ("PREST-010", "SARL Mobilier Pro", "Bali, Douala", "233 699 012 345", "mobilier.pro@yahoo.fr"),
    ("PREST-011", "Formation Elite Cameroun", "Deido, Douala", "233 677 111 222", "formation.elite@gmail.com"),
    ("PREST-012", "Pharma Distribution SA", "Akwa, Douala", "233 655 222 333", "pharma.distrib@cm.com"),
    ("PREST-013", "Nettoyage Pro Services", "Bonaberi, Douala", "233 699 333 444", "nettoyage.pro@gmail.com"),
    ("PREST-014", "Cabinet Juridique Etoa & Associés", "Bonanjo, Douala", "233 677 444 555", "etoa.associes@yahoo.fr"),
    ("PREST-015", "Restauration Collective Cam", "Akwa, Douala", "233 655 555 666", "restau.collective@gmail.com"),
]


# (tache_numero, objet, montant_estime, statut_da, offres, bc_data, motif_refus)
SCENARIOS = [
    # --- 3 DA créées ---
    ("3215003", "Acquisition de 10 ordinateurs portables pour la DRH", 15_000_000, 'cree', [], None, None),
    ("3211044", "Achat de fournitures de bureau pour le trimestre 2", 800_000, 'cree', [], None, None),
    ("3213007", "Campagne de sensibilisation santé bucco-dentaire", 2_500_000, 'cree', [], None, None),

    # --- 3 DA en étude ---
    ("3212004", "Formation en gestion de projets pour 15 cadres", 12_000_000, 'en_etude', [
        ("PREST-005", 11_500_000, 'recue'),
        ("PREST-011", 13_200_000, 'recue'),
        ("PREST-009", None, 'en_attente'),
    ], None, None),
    ("3213003", "Approvisionnement en produits pharmaceutiques", 25_000_000, 'en_etude', [
        ("PREST-004", 23_800_000, 'recue'),
        ("PREST-012", 24_500_000, 'recue'),
    ], None, None),
    ("3214005", "Location de salle pour tournoi sportif inter-services", 3_500_000, 'en_etude', [
        ("PREST-007", 3_200_000, 'recue'),
        ("PREST-006", None, 'en_attente'),
    ], None, None),

    # --- 3 DA validées (offre retenue, pas encore de BC) ---
    ("3211038", "Audit des risques professionnels", 5_000_000, 'validee', [
        ("PREST-005", 4_800_000, 'retenue'),
        ("PREST-014", 5_500_000, 'refusee'),
    ], None, None),
    ("3212008", "Pécules stagiaires session mars-mai 2026", 6_000_000, 'validee', [
        ("PREST-001", 5_950_000, 'retenue'),
    ], None, None),
    ("3213009", "Achat de matériel d'entretien hospitalier", 7_500_000, 'validee', [
        ("PREST-013", 7_200_000, 'retenue'),
        ("PREST-010", 8_100_000, 'refusee'),
    ], None, None),

    # --- 5 BC créés / notifiés / en cours ---
    ("3215003", "Achat de consommables informatiques", 8_000_000, 'bc_cree',
     [("PREST-002", 7_500_000, 'retenue'), ("PREST-009", 8_200_000, 'refusee')],
     {'statut': 'cree', 'montant_ht': 6_302_521, 'date_emission': date(2026, 2, 15),
      'delai': 21, 'imputations': [("6055020", 6_302_521)]}, None),
    ("3212002", "Hébergement formateurs CNUCED - Session avril", 6_000_000, 'bc_cree',
     [("PREST-007", 5_800_000, 'retenue')],
     {'statut': 'notifie', 'montant_ht': 4_873_950, 'date_emission': date(2026, 3, 1),
      'date_notification': date(2026, 3, 5), 'delai': 30,
      'imputations': [("6383001", 4_873_950)]}, None),
    ("3213003", "Achat de réactifs de laboratoire", 12_000_000, 'bc_cree',
     [("PREST-012", 11_500_000, 'retenue'), ("PREST-004", 12_800_000, 'refusee')],
     {'statut': 'en_cours', 'montant_ht': 9_663_866, 'date_emission': date(2026, 1, 20),
      'date_notification': date(2026, 1, 25), 'delai': 60,
      'imputations': [("6055030", 9_663_866)]}, None),
    ("3214005", "Acquisition matériel sportif", 8_000_000, 'bc_cree',
     [("PREST-010", 7_800_000, 'retenue')],
     {'statut': 'en_cours', 'montant_ht': 6_554_622, 'date_emission': date(2026, 2, 10),
      'date_notification': date(2026, 2, 15), 'delai': 45,
      'imputations': [("6058000", 6_554_622)]}, None),
    ("3215003", "Achat de fournitures de bureau direct", 5_000_000, 'bc_cree',
     [("PREST-001", 4_600_000, 'retenue'), ("PREST-003", 5_200_000, 'refusee')],
     {'statut': 'notifie', 'montant_ht': 3_865_546, 'date_emission': date(2026, 4, 1),
      'date_notification': date(2026, 4, 5), 'delai': 21,
      'imputations': [("6055010", 3_865_546)]}, None),

    # --- 4 BC exécutés ---
    ("3212002", "Indemnités formateurs CNUCED - Trimestre 1", 30_000_000, 'bc_cree',
     [("PREST-011", 28_414_750, 'retenue')],
     {'statut': 'execute', 'montant_ht': 23_865_546, 'date_emission': date(2026, 1, 10),
      'date_notification': date(2026, 1, 12), 'delai': 90,
      'imputations': [("6585100", 23_865_546)]}, None),
    ("3212004", "Formation Excel avancé - 20 agents", 5_000_000, 'bc_cree',
     [("PREST-011", 4_800_000, 'retenue')],
     {'statut': 'execute', 'montant_ht': 4_033_613, 'date_emission': date(2026, 2, 1),
      'date_notification': date(2026, 2, 3), 'delai': 14,
      'imputations': [("6330100", 4_033_613)]}, None),
    ("3211004", "Prise en charge obsèques agent - Famille Nkotto", 2_500_000, 'bc_cree',
     [("PREST-007", 2_150_000, 'retenue')],
     {'statut': 'execute', 'montant_ht': 1_806_723, 'date_emission': date(2026, 1, 28),
      'date_notification': date(2026, 1, 29), 'delai': 7,
      'imputations': [("6588000", 1_806_723)]}, None),
    ("3214009", "Don pour la journée de la femme 2026", 3_500_000, 'bc_cree',
     [("PREST-007", 3_000_000, 'retenue')],
     {'statut': 'execute', 'montant_ht': 2_521_008, 'date_emission': date(2026, 3, 1),
      'date_notification': date(2026, 3, 2), 'delai': 5,
      'imputations': [("6581111", 2_521_008)]}, None),

    # --- 2 BC annulés ---
    ("3213006", "Évacuation sanitaire agent Mballa - Annulée", 15_000_000, 'bc_cree',
     [("PREST-008", 14_500_000, 'retenue')],
     {'statut': 'annule', 'montant_ht': 12_184_874, 'date_emission': date(2026, 2, 20),
      'date_notification': date(2026, 2, 22), 'delai': 30,
      'motif_annulation': "Prise en charge finalement assurée par la CNPS",
      'imputations': [("6684200", 12_184_874)]}, None),
    ("3212034", "Séminaire leadership - Reporté au S2", 2_000_000, 'bc_cree',
     [("PREST-005", 1_800_000, 'retenue')],
     {'statut': 'annule', 'montant_ht': 1_512_605, 'date_emission': date(2026, 3, 15),
      'delai': 14,
      'motif_annulation': "Séminaire reporté au second semestre suite à indisponibilité du formateur",
      'imputations': [("6266000", 1_512_605)]}, None),

    # --- 1 DA refusée ---
    ("3211037", "Acquisition logiciel SIRH - Budget insuffisant", 350_000_000, 'refusee',
     [("PREST-009", 340_000_000, 'recue'), ("PREST-002", 380_000_000, 'recue')],
     None, "Le montant estimé dépasse le plafond autorisé. À revoir avec la Direction Générale."),
]


# (tache_source, ligne_source_code, tache_dest, ligne_dest_code, montant, motif)
VIREMENTS = [
    ("3211004", "6588000", "3211004", "6641100", 16_500_000,
     "Réallocation pour couverture des charges sociales obsèques"),
    ("3211025", "6588000", "3211009", "6612500", 3_319_458,
     "Transfert pour financement des gratifications et médailles"),
    ("3215003", "6055010", "3212002", "6383001", 5_000_000,
     "Renforcement budget missions programme CNUCED"),
]


class Command(BaseCommand):
    help = "Génère des scénarios de démo réalistes (à lancer APRÈS seed_real_data)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset', action='store_true',
            help='Supprime les DA/BC/Offres/Prestataires démos existants avant la création.'
        )

    @transaction.atomic
    def handle(self, *args, **options):
        # --- Pré-requis ---
        exercice = ExerciceBudgetaire.objects.filter(annee=2026).first()
        if not exercice:
            self.stderr.write(self.style.ERROR(
                "Aucun exercice 2026 trouvé. Lance d'abord : python manage.py seed_real_data"
            ))
            return
        if not Tache.objects.filter(exercice=exercice).exists():
            self.stderr.write(self.style.ERROR(
                "Aucune tâche trouvée pour 2026. Lance d'abord : python manage.py seed_real_data"
            ))
            return

        admin_user = (
            Utilisateur.objects.filter(role='admin').first()
            or Utilisateur.objects.filter(is_superuser=True).first()
            or Utilisateur.objects.first()
        )
        if not admin_user:
            self.stderr.write(self.style.ERROR("Aucun utilisateur en base."))
            return

        directeur = Utilisateur.objects.filter(role='directeur_drh').first() or admin_user
        assistante = Utilisateur.objects.filter(role='assistante_drh').first() or admin_user

        # --- Reset éventuel ---
        if options['reset']:
            self.stdout.write("Réinitialisation des scénarios précédents...")
            BonCommande.objects.filter(exercice=exercice).delete()
            DemandeAchat.objects.filter(exercice=exercice).delete()
            VirementBudgetaire.objects.filter(exercice=exercice).delete()
            Prestataire.objects.filter(code__startswith='PREST-').delete()
            Alerte.objects.all().delete()
            JournalActivite.objects.filter(type_action__in=[
                'DA.create', 'DA.transition', 'BC.create', 'BC.transition',
                'Offre.create', 'Offre.transition', 'Virement',
            ]).delete()

        # ─── 1. PRESTATAIRES ───────────────────────────────────────────────
        self.stdout.write("Création des prestataires...")
        prest_by_code = {}
        created_prest = 0
        for code, nom, adresse, tel, email in PRESTATAIRES:
            p, was_created = Prestataire.objects.get_or_create(
                code=code,
                defaults={'nom': nom, 'adresse': adresse, 'telephone': tel, 'email': email},
            )
            prest_by_code[code] = p
            if was_created:
                created_prest += 1
        self.stdout.write(f"  -> {created_prest} prestataires créés ({len(prest_by_code)} au total)")

        # ─── 2. SCÉNARIOS DA + OFFRES + BC ────────────────────────────────
        self.stdout.write("Création des scénarios DA / offres / BC...")
        da_counter = 1
        bc_counter = 1
        nb_da = nb_offres = nb_bc = nb_imp = 0

        for tache_num, objet, est, statut_da, offres_data, bc_data, motif in SCENARIOS:
            tache = Tache.objects.filter(exercice=exercice, numero=tache_num).first()
            if not tache:
                self.stdout.write(f"  ! Tâche {tache_num} introuvable - scénario ignoré")
                continue

            # DA — get_or_create pour idempotence
            ref = f"DA-2026-{da_counter:03d}"
            da, da_created = DemandeAchat.objects.get_or_create(
                reference=ref,
                defaults={
                    'exercice': exercice, 'tache': tache,
                    'objet': objet, 'montant_estime': Decimal(est),
                    'statut': statut_da, 'motif_refus': motif or '',
                    'created_by': assistante,
                },
            )
            da_counter += 1
            if da_created:
                nb_da += 1
                JournalActivite.objects.create(
                    type_action='DA.create', utilisateur=assistante,
                    description=f"Création DA {ref} — {objet[:50]}",
                    entite_type='da', entite_id=da.pk,
                )

            # OFFRES — ne créer que si la DA vient d'être créée
            if da_created:
                for code_prest, montant_offre, statut_offre in offres_data:
                    p = prest_by_code.get(code_prest)
                    if not p:
                        continue
                    kwargs = {
                        'demande': da, 'prestataire': p,
                        'statut': statut_offre,
                    }
                    if montant_offre is not None:
                        kwargs['montant'] = Decimal(montant_offre)
                    if statut_offre in ('recue', 'retenue', 'refusee'):
                        kwargs['date_reception'] = timezone.now() - timedelta(days=3)
                    if statut_offre == 'refusee':
                        kwargs['motif_refus'] = "Tarif supérieur à l'offre concurrente"
                    Offre.objects.create(**kwargs)
                    nb_offres += 1

            # BC (si scénario en a un) — get_or_create par numéro
            if bc_data:
                offre_retenue = da.offres.filter(statut='retenue').first()
                if not offre_retenue:
                    continue
                montant_ht = Decimal(bc_data['montant_ht'])
                tva = montant_ht * Decimal('0.1925')
                ttc = montant_ht + tva
                date_emission = bc_data['date_emission']
                delai = bc_data.get('delai')
                date_notif = bc_data.get('date_notification')
                date_echeance = None
                if delai and date_notif:
                    date_echeance = date_notif + timedelta(days=delai)
                elif delai:
                    date_echeance = date_emission + timedelta(days=delai)

                numero = f"BC-2026-{bc_counter:04d}"
                bc, bc_created = BonCommande.objects.get_or_create(
                    numero=numero,
                    defaults={
                        'demande': da, 'tache': tache,
                        'exercice': exercice, 'prestataire': offre_retenue.prestataire,
                        'date_notification': date_notif,
                        'delai_execution_jours': delai,
                        'date_echeance': date_echeance,
                        'montant_ht': montant_ht, 'montant_tva': tva, 'montant_ttc': ttc,
                        'statut': bc_data['statut'],
                        'motif_annulation': bc_data.get('motif_annulation', ''),
                    },
                )
                bc_counter += 1
                if bc_created:
                    # Override de la date_emission (auto_now_add)
                    BonCommande.objects.filter(pk=bc.pk).update(date_emission=date_emission)
                    nb_bc += 1

                    # Imputations sur les lignes budgétaires de la tâche
                    # Les imputations doivent totaliser le montant TTC du BC
                    imp_list = bc_data.get('imputations', [])
                    for idx_imp, (code_nature, _) in enumerate(imp_list):
                        ligne = LigneBudgetaire.objects.filter(
                            tache=tache, code_nature=code_nature, actif=True
                        ).first()
                        if ligne:
                            # Si une seule imputation, utiliser le TTC complet
                            montant_imp = ttc if len(imp_list) == 1 else Decimal(_)
                            ImputationBC.objects.create(
                                bon_commande=bc, ligne_budgetaire=ligne,
                                montant=montant_imp,
                            )
                            nb_imp += 1

                    JournalActivite.objects.create(
                        type_action='BC.create', utilisateur=assistante,
                        description=f"Création BC {numero} — {offre_retenue.prestataire.nom[:40]}",
                        entite_type='bc', entite_id=bc.pk,
                    )
                    if bc.statut != 'cree':
                        JournalActivite.objects.create(
                            type_action='BC.notify', utilisateur=directeur,
                            description=f"BC {numero} -> {bc.get_statut_display()}",
                            entite_type='bc', entite_id=bc.pk,
                        )

        self.stdout.write(f"  -> {nb_da} DA, {nb_offres} offres, {nb_bc} BC, {nb_imp} imputations")

        # ─── 3. VIREMENTS BUDGÉTAIRES ─────────────────────────────────────
        self.stdout.write("Création des virements...")
        nb_vir = 0
        for ts_num, ls_code, td_num, ld_code, montant, motif in VIREMENTS:
            ts = Tache.objects.filter(exercice=exercice, numero=ts_num).first()
            td = Tache.objects.filter(exercice=exercice, numero=td_num).first()
            if not (ts and td):
                continue
            ls = LigneBudgetaire.objects.filter(tache=ts, code_nature=ls_code).first()
            ld = LigneBudgetaire.objects.filter(tache=td, code_nature=ld_code).first()
            if not (ls and ld):
                self.stdout.write(f"  ! Lignes introuvables pour {ts_num}/{ls_code} -> {td_num}/{ld_code}")
                continue
            VirementBudgetaire.objects.create(
                exercice=exercice, ligne_source=ls, ligne_destination=ld,
                montant=Decimal(montant), motif=motif,
                created_by=directeur,
            )
            nb_vir += 1
            JournalActivite.objects.create(
                type_action='Virement', utilisateur=directeur,
                description=f"Virement {ls_code}->{ld_code} : {montant:,} FCFA",
                entite_type='virement', entite_id=0,
            )
        self.stdout.write(f"  -> {nb_vir} virements")

        # ─── 4. PROLONGATION DE BC ────────────────────────────────────────
        bc_a_prolonger = BonCommande.objects.filter(
            exercice=exercice, statut='en_cours', date_echeance__isnull=False
        ).first()
        if bc_a_prolonger:
            ancienne = bc_a_prolonger.date_echeance
            nouvelle = ancienne + timedelta(days=15)
            ProlongationBC.objects.create(
                bon_commande=bc_a_prolonger,
                ancienne_echeance=ancienne,
                nouvelle_echeance=nouvelle,
                duree_prolongation_jours=15,
                motif="Retard de livraison côté fournisseur — délai supplémentaire accordé.",
                created_by=directeur,
            )
            BonCommande.objects.filter(pk=bc_a_prolonger.pk).update(date_echeance=nouvelle)
            self.stdout.write(f"  -> 1 prolongation sur {bc_a_prolonger.numero}")

        # ─── 5. ALERTES (sur tâches très consommées) ──────────────────────
        self.stdout.write("Génération des alertes...")
        nb_alertes = 0
        for tache in Tache.objects.filter(exercice=exercice).with_aggregates():
            taux = float(tache.taux_consommation)
            if taux >= 80:
                Alerte.objects.get_or_create(
                    tache=tache, type_alerte='seuil',
                    defaults={
                        'message': f"Tâche en surconsommation ({taux:.1f}%)",
                        'seuil_atteint': Decimal(f"{taux:.2f}"),
                        'lu': False,
                    },
                )
                nb_alertes += 1
        self.stdout.write(f"  -> {nb_alertes} alertes")

        # ─── 6. NOTIFICATION DE BIENVENUE ─────────────────────────────────
        for user in Utilisateur.objects.filter(is_active=True):
            Notification.objects.get_or_create(
                utilisateur=user, type='info',
                titre='Données de démo chargées',
                defaults={
                    'message': "Le jeu de scénarios de démonstration est prêt. "
                               "Naviguez dans les bilans, BC, DA pour explorer.",
                    'lu': False,
                },
            )

        # ─── Récapitulatif ────────────────────────────────────────────────
        self.stdout.write(self.style.SUCCESS("\n=== Scénarios créés ==="))
        self.stdout.write(f"Prestataires : {Prestataire.objects.count()}")
        self.stdout.write(f"DA          : {DemandeAchat.objects.filter(exercice=exercice).count()}")
        self.stdout.write(f"Offres      : {Offre.objects.filter(demande__exercice=exercice).count()}")
        self.stdout.write(f"BC          : {BonCommande.objects.filter(exercice=exercice).count()}")
        self.stdout.write(f"Imputations : {ImputationBC.objects.filter(bon_commande__exercice=exercice).count()}")
        self.stdout.write(f"Virements   : {VirementBudgetaire.objects.filter(exercice=exercice).count()}")
        self.stdout.write(f"Alertes     : {Alerte.objects.count()}")
        self.stdout.write(self.style.SUCCESS("Demo prete."))
