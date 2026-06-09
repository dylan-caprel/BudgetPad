"""
Seed des données RÉELLES du PAD — Exercice 2026 (Direction des Ressources Humaines).

Sources officielles figées dans ``core/management/commands/data/`` :

  • pad_2026_taches.json   — Suivi détaillé des tâches (PDF officiel « DRH », période
                             du 01/01/2026 au 08/06/2026) : 58 tâches, 130 lignes
                             budgétaires, transferts et consommations réels
                             (structure réconciliée à 100 % avec l'export CSV).
  • pad_2026_journal.json  — Journal de programmation par bons de commande
                             (Excel « JP-BC DRH 2026 ») : 36 prestations programmées.

Fidélité de la reconstruction
-----------------------------
  • montant_initial      = budget initial réel (colonne « Budget 2026 » du PDF).
  • Les transferts sont reconstitués en VirementBudgetaire via un appariement
    équilibré (transport) : chaque ligne retrouve EXACTEMENT son transfert + / −.
    Le transfert hors-périmètre DRH de la tâche 3112006 (DONS, 10 000 000 FCFA),
    qui n'a pas de contrepartie interne, est intégré au budget initial de la ligne
    — seul moyen d'équilibrer sans créer de ligne fictive.
  • Les consommations réelles sont créées en ConsommationDirecte.

  ⇒ L'application recalcule un budget ajusté / consommation / solde / taux
    strictement identiques au suivi officiel du PAD.

Usage
-----
    python manage.py seed_real_data            # (ré)initialise l'exercice 2026 (upsert)
    python manage.py seed_real_data --reset    # état officiel PUR : supprime d'abord le
                                               # procurement de démo (DA/BC) et les tâches
                                               # parasites de 2026, puis recharge l'officiel
    python manage.py seed_real_data --flush    # vide TOUTE la base puis recharge
"""
import json
from decimal import Decimal
from datetime import date
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

DATA_DIR = Path(__file__).resolve().parent / 'data'

# Transferts « hors périmètre DRH » intégrés au budget initial (équilibrage).
# (numero_tache, code_nature) dont le transfert sortant n'a pas de contrepartie DRH.
EXTERNAL_BAKE = {('3112006', '6581111')}

# Comptes de démonstration : (username, rôle, nom complet)
COMPTES = [
    ('admin',      'admin',          'Dylan Caprel Ngando'),
    ('directeur',  'directeur_drh',  'Marie-Claire Etoa'),
    ('chef',       'chef_service',   'Robert Essomba'),
    ('assistante', 'assistante_drh', 'Florence Mbarga'),
    ('lecteur',    'lecteur',        'Auditeur Externe'),
]
MOT_DE_PASSE = 'Pad2025@'

PRESTATAIRES_DEMO = [
    ('PREST-001', 'SARL Papeterie Centrale', 'Rue Njo Njo, Douala',      '+237 233 401 234', 'papeterie@example.cm'),
    ('PREST-002', 'Clinique Bonanjo',        'Avenue de Gaulle, Douala', '+237 233 421 000', 'clinique@example.cm'),
    ('PREST-003', 'Tech Solutions SARL',     'Akwa, Douala',             '+237 233 511 200', 'tech@example.cm'),
    ('PREST-004', 'Bureau Plus',             'Bali, Douala',             '+237 233 601 000', 'bureau@example.cm'),
    ('PREST-005', 'Groupe Santé PAD',        'Bonanjo, Douala',          '+237 233 701 500', 'sante@example.cm'),
]


def D(x):
    return Decimal(str(x))


class Command(BaseCommand):
    help = "Charge les données réelles DRH PAD — Exercice 2026 (tâches, transferts, consommations, journal)."

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Vide TOUTE la base avant de charger (ATTENTION : supprime tout).',
        )
        parser.add_argument(
            '--reset', action='store_true',
            help="État officiel pur : supprime le procurement (DA/BC) et les tâches "
                 "non officielles de l'exercice 2026 avant de recharger.",
        )

    def handle(self, *args, **options):
        from core.models import (
            Utilisateur, ExerciceBudgetaire, Tache, LigneBudgetaire,
            VirementBudgetaire, ConsommationDirecte, Prestataire, PrestationProgrammee,
        )

        try:
            taches_data = json.loads((DATA_DIR / 'pad_2026_taches.json').read_text(encoding='utf-8'))
            journal_data = json.loads((DATA_DIR / 'pad_2026_journal.json').read_text(encoding='utf-8'))
        except FileNotFoundError as e:
            raise CommandError(f"Fichier de données introuvable : {e}")

        if options['flush']:
            self._flush()

        with transaction.atomic():
            admin = self._creer_utilisateurs(Utilisateur)
            exercice = self._creer_exercice(ExerciceBudgetaire, taches_data)
            if options['reset']:
                self._reset_officiel(exercice, {t['numero'] for t in taches_data})
            # Purge ciblée des données dérivées 2026 (idempotence sans --flush)
            PrestationProgrammee.objects.filter(exercice=exercice).delete()
            ConsommationDirecte.objects.filter(ligne_budgetaire__tache__exercice=exercice).delete()
            VirementBudgetaire.objects.filter(exercice=exercice).delete()

            lignes_map = self._creer_taches_lignes(exercice, Tache, LigneBudgetaire, taches_data)
            n_vir = self._creer_virements(exercice, VirementBudgetaire, lignes_map, taches_data, admin)
            n_conso, conso_total = self._creer_consommations(ConsommationDirecte, lignes_map, taches_data, admin)
            self._creer_prestataires(Prestataire)
            n_presta, n_link = self._creer_journal(exercice, PrestationProgrammee, lignes_map, journal_data)

        n_taches = len(taches_data)
        n_lignes = sum(len(t['lignes']) for t in taches_data)
        self.stdout.write(self.style.SUCCESS(
            "\n  Seed reel PAD 2026 termine :\n"
            f"  - Exercice 2026 actif (budget global {int(exercice.montant_global):,} FCFA)\n"
            f"  - {n_taches} taches / {n_lignes} lignes budgetaires\n"
            f"  - {n_vir} virements (transferts reconstitues)\n"
            f"  - {n_conso} consommations directes ({int(conso_total):,} FCFA)\n"
            f"  - {n_presta} prestations au journal ({n_link} liees a une ligne)\n"
            f"  - {len(COMPTES)} comptes (mot de passe : {MOT_DE_PASSE})\n"
            f"  - {len(PRESTATAIRES_DEMO)} prestataires de demonstration\n"
        ).replace(',', ' '))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _flush(self):
        """Supprime toutes les données métier dans un ordre compatible avec les FK PROTECT."""
        from core.models import (
            Utilisateur, ExerciceBudgetaire, Tache, LigneBudgetaire, VirementBudgetaire,
            ConsommationDirecte, Prestataire, PrestationProgrammee, DemandeAchat, Offre,
            BonCommande, LigneBC, ImputationBC, ProlongationBC, PieceJointe, Sequence,
        )
        self.stdout.write(self.style.WARNING("  Vidage complet de la base..."))
        for model in [
            PrestationProgrammee, ImputationBC, ConsommationDirecte, VirementBudgetaire,
            LigneBC, ProlongationBC, Offre, BonCommande, DemandeAchat,
            LigneBudgetaire, Tache, Prestataire, PieceJointe,
            ExerciceBudgetaire, Sequence, Utilisateur,
        ]:
            model.objects.all().delete()

    def _reset_officiel(self, exercice, numeros_officiels):
        """Supprime le procurement de démo et les tâches non officielles de l'exercice
        (ordre compatible avec les FK PROTECT) pour repartir d'un état officiel pur."""
        from core.models import (
            Tache, LigneBudgetaire, VirementBudgetaire, ConsommationDirecte,
            PrestationProgrammee, DemandeAchat, Offre, BonCommande, LigneBC,
            ImputationBC, ProlongationBC,
        )
        self.stdout.write("  [reset] Suppression du procurement de démo et des tâches parasites 2026...")
        PrestationProgrammee.objects.filter(exercice=exercice).delete()
        ImputationBC.objects.filter(bon_commande__exercice=exercice).delete()
        LigneBC.objects.filter(bon_commande__exercice=exercice).delete()
        ProlongationBC.objects.filter(bon_commande__exercice=exercice).delete()
        ConsommationDirecte.objects.filter(ligne_budgetaire__tache__exercice=exercice).delete()
        VirementBudgetaire.objects.filter(exercice=exercice).delete()
        Offre.objects.filter(demande__exercice=exercice).delete()
        BonCommande.objects.filter(exercice=exercice).delete()
        DemandeAchat.objects.filter(exercice=exercice).delete()
        # Tâches non présentes dans les données officielles (parasites) — cascade sur leurs lignes
        parasites = Tache.objects.filter(exercice=exercice).exclude(numero__in=numeros_officiels)
        nb = parasites.count()
        parasites.delete()
        if nb:
            self.stdout.write(f"  [reset] {nb} tache(s) parasite(s) supprimee(s).")

    def _creer_utilisateurs(self, Utilisateur):
        self.stdout.write("  Comptes utilisateurs...")
        admin = None
        for username, role, nom in COMPTES:
            u = Utilisateur.objects.filter(username=username).first()
            if u is None:
                u = Utilisateur.objects.create_user(
                    username=username, password=MOT_DE_PASSE,
                    role=role, nom_complet=nom, must_change_password=False,
                )
            else:
                u.role = role
                u.nom_complet = nom
                u.must_change_password = False
                u.set_password(MOT_DE_PASSE)
            if username == 'admin':
                u.is_staff = True
                u.is_superuser = True
            u.save()
            if username == 'admin':
                admin = u
        return admin

    def _creer_exercice(self, ExerciceBudgetaire, taches_data):
        self.stdout.write("  Exercice 2026...")
        total = Decimal('0')
        for t in taches_data:
            for l in t['lignes']:
                total += self._montant_initial_stocke(t['numero'], l)
        # Règle R7 : un seul exercice actif
        ExerciceBudgetaire.objects.exclude(annee=2026).update(is_active=False)
        ex, _ = ExerciceBudgetaire.objects.update_or_create(
            annee=2026,
            defaults={
                'date_debut': date(2026, 1, 1),
                'date_fin': date(2026, 12, 31),
                'montant_global': total,
                'statut': 'actif',
                'is_active': True,
                'is_locked': False,
            },
        )
        return ex

    @staticmethod
    def _montant_initial_stocke(numero, ligne):
        """Budget initial stocké : réel, sauf transfert externe intégré (cf. EXTERNAL_BAKE)."""
        init = D(ligne['montant_initial'])
        if (numero, ligne['code_nature']) in EXTERNAL_BAKE:
            init = init + D(ligne['transfert_plus']) - D(ligne['transfert_moins'])
        return init

    def _creer_taches_lignes(self, exercice, Tache, LigneBudgetaire, taches_data):
        self.stdout.write(f"  {len(taches_data)} taches et leurs lignes...")
        lignes_map = {}
        for t in taches_data:
            tache, _ = Tache.objects.update_or_create(
                exercice=exercice, numero=t['numero'],
                defaults={'titre': t['titre'], 'actif': True},
            )
            for l in t['lignes']:
                ligne, _ = LigneBudgetaire.objects.update_or_create(
                    tache=tache, code_nature=l['code_nature'],
                    defaults={
                        'libelle_nature': l['libelle_nature'],
                        'montant_initial': self._montant_initial_stocke(t['numero'], l),
                        'actif': True,
                    },
                )
                lignes_map[(t['numero'], l['code_nature'])] = ligne
        return lignes_map

    def _creer_virements(self, exercice, VirementBudgetaire, lignes_map, taches_data, admin):
        """Reconstitue les transferts par appariement équilibré (problème de transport)."""
        self.stdout.write("  Virements (reconstruction des transferts)...")
        givers, receivers = [], []
        for t in taches_data:
            for l in t['lignes']:
                key = (t['numero'], l['code_nature'])
                if key in EXTERNAL_BAKE:
                    continue
                tp, tm = D(l['transfert_plus']), D(l['transfert_moins'])
                if tm > 0:
                    givers.append([lignes_map[key], tm])
                if tp > 0:
                    receivers.append([lignes_map[key], tp])

        somme_g = sum(g[1] for g in givers)
        somme_r = sum(r[1] for r in receivers)
        if somme_g != somme_r:
            raise CommandError(
                f"Transferts déséquilibrés ({somme_g} sortant != {somme_r} entrant). "
                f"Vérifiez EXTERNAL_BAKE."
            )

        motif = "Réaménagement budgétaire — exercice 2026 (réf. suivi détaillé DRH)"
        count = 0
        # Stratégie « plus gros donneur → plus gros receveur différent » : draine tôt
        # les grosses lignes mixtes (donneuse ET receveuse) et évite l'auto-appariement.
        while True:
            givers = [g for g in givers if g[1] > 0]
            receivers = [r for r in receivers if r[1] > 0]
            if not givers:
                break
            g = max(givers, key=lambda x: x[1])
            candidats = [r for r in receivers if r[0].pk != g[0].pk]
            if not candidats:
                raise CommandError(
                    f"Appariement impossible : reliquat {g[1]} sur la ligne {g[0]} "
                    f"(aucun receveur distinct disponible)."
                )
            r = max(candidats, key=lambda x: x[1])
            x = min(g[1], r[1])
            VirementBudgetaire.objects.create(
                exercice=exercice, ligne_source=g[0], ligne_destination=r[0],
                montant=x, motif=motif, created_by=admin,
            )
            g[1] -= x
            r[1] -= x
            count += 1
        return count

    def _creer_consommations(self, ConsommationDirecte, lignes_map, taches_data, admin):
        self.stdout.write("  Consommations directes réelles...")
        count, total = 0, Decimal('0')
        for t in taches_data:
            for l in t['lignes']:
                conso = D(l['consommation'])
                if conso <= 0:
                    continue
                ConsommationDirecte.objects.create(
                    ligne_budgetaire=lignes_map[(t['numero'], l['code_nature'])],
                    montant=conso, motif='achat_direct',
                    description="Consommation réelle au 08/06/2026 — import suivi détaillé DRH 2026",
                    date_consommation=date(2026, 6, 8),
                    created_by=admin, est_annule=False,
                )
                count += 1
                total += conso
        return count, total

    def _creer_prestataires(self, Prestataire):
        self.stdout.write("  Prestataires de démonstration...")
        for code, nom, adresse, tel, email in PRESTATAIRES_DEMO:
            Prestataire.objects.update_or_create(
                code=code,
                defaults={'nom': nom, 'adresse': adresse, 'telephone': tel, 'email': email},
            )

    def _creer_journal(self, exercice, PrestationProgrammee, lignes_map, journal_data):
        self.stdout.write(f"  Journal de programmation ({len(journal_data)} prestations)...")
        count, linked = 0, 0
        for row in journal_data:
            ligne = lignes_map.get((row['code_tache'], row['code_nature']))
            bp = row.get('budget_previsionnel')
            PrestationProgrammee.objects.update_or_create(
                exercice=exercice, numero_ligne=row['numero_ligne'],
                defaults={
                    'code_tache': row['code_tache'],
                    'libelle_tache': row['libelle_tache'],
                    'code_nature': row['code_nature'],
                    'libelle_nature': row['libelle_nature'],
                    'objet_prestation': row['objet_prestation'],
                    'nature_prestation': row['nature_prestation'] or 'APPRO',
                    'montant_ht': D(row['montant_ht']),
                    'budget_previsionnel': (D(bp) if bp else None),
                    'periode': row['periode'],
                    'priorite': row['priorite'],
                    'statut': 'programmee',
                    'ligne_budgetaire': ligne,
                },
            )
            count += 1
            if ligne:
                linked += 1
        return count, linked
