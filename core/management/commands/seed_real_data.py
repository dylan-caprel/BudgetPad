"""
Seed avec les données RÉELLES du PAD — Exercice 2026 DRH.
Budget total : 6 737 266 993 FCFA (49 tâches, données officielles).

Usage :
    python manage.py seed_real_data
    python manage.py seed_real_data --flush   # vide la DB avant
"""
from decimal import Decimal
from datetime import date, timedelta
from django.core.management.base import BaseCommand
from django.db import transaction
from django.contrib.auth.hashers import make_password


# ─── Données extraites du PDF officiel DRH PAD 2026 ───────────────────────────
TACHES_2026 = [
    {
        "numero": "3101069",
        "titre": "REVISION DE LA CONVENTION COLLECTIVE",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 686054),
        ],
    },
    {
        "numero": "3101070",
        "titre": "ELABORATION D'UN RECUEIL DE TEXTES RH ET MISE A JOUR PERIODIQUE DU RECUEIL",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6266000", "DOCUMENTATION GENERALE ET TECHNIQUE", 5000000),
        ],
    },
    {
        "numero": "3112006",
        "titre": "ASSISTANCE SOCIALE",
        "lignes": [
            ("6581111", "DONS", 20000000),
        ],
    },
    {
        "numero": "3202030",
        "titre": "ELABORATION DU BILAN SOCIAL DU GROUPE PAD",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3211001",
        "titre": "ACTIVITES AVEC LES PARTENAIRES SOCIAUX",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 189800),
            ("6271020", "EPI SPECIALISES", 270000),
            ("6588000", "AUTRES CHARGES DIVERSES", 5000000),
        ],
    },
    {
        "numero": "3211004",
        "titre": "GESTION DES OBSEQUES",
        "lignes": [
            ("6588000", "AUTRES CHARGES DIVERSES", 20000000),
            ("6641100", "AUTRES CHARGES SOCIALES", 2000000),
        ],
    },
    {
        "numero": "3211009",
        "titre": "RECOMPENSES ET DISTINCTIONS HONORIFIQUES",
        "lignes": [
            ("6612500", "GRATIFICATIONS", 0),
        ],
    },
    {
        "numero": "3211010",
        "titre": "LIQUIDATION DES DROITS DU PERSONNEL",
        "lignes": [
            ("6614000", "DROITS ET PRIMES SEPARATION", 1479000000),
        ],
    },
    {
        "numero": "3211015",
        "titre": "RESTAURATION, CLASSEMENT ET CONSERVATION DES DOCUMENTS DE LA PAIE",
        "lignes": [
            ("6043000", "PRODUITS D'ENTRETIEN SUR STOCK", 160260),
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3211018",
        "titre": "CHARGES PATRONALES",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3211022",
        "titre": "GESTION DE LA DISCIPLINE",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3211024",
        "titre": "SUIVI DES OPERATIONS RELATIVES A L'ASSAINISSEMENT DE L'ENVIRONNEMENT DU TRAVAIL",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6271020", "EPI SPECIALISES", 500000),
        ],
    },
    {
        "numero": "3211025",
        "titre": "ORGANISATION DES ELECTIONS DES DELEGUES DU PERSONNEL",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 748154),
            ("6058000", "ACHATS MATERIELS ET EQUIPEMENTS", 1000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 3650000),
        ],
    },
    {
        "numero": "3211026",
        "titre": "ORGANISATION DES ELECTIONS DU REPRESENTANT DU PERSONNEL AU CA",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 748154),
            ("6588000", "AUTRES CHARGES DIVERSES", 2300000),
        ],
    },
    {
        "numero": "3211029",
        "titre": "PROCESSUS DE SELECTION DES CANDIDATS PRESSENTIS AU RECRUTEMENT AU PAD",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6588000", "AUTRES CHARGES DIVERSES", 1000000),
        ],
    },
    {
        "numero": "3211030",
        "titre": "ANALYSES ET REQUETES",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3211036",
        "titre": "SUIVI DES PRESENCES ET REQUETTES DU PERSONNEL",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 250000),
        ],
    },
    {
        "numero": "3211037",
        "titre": "MODERNISATION DE LA GESTION DES RESSOURCES HUMAINES",
        "lignes": [
            ("2131000", "LOGICIELS INFORMATIQUES", 400000000),
        ],
    },
    {
        "numero": "3211038",
        "titre": "ANALYSE ET EVALUATION DES RISQUES PROFESSIONNELS AU PAD",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6324130", "HONORAIRES / CONSEILS / COMMISSIONS", 5000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 1000000),
        ],
    },
    {
        "numero": "3211039",
        "titre": "ASSISTANCE DANS L'ELABORATION D'UNE DEMARCHE GPEC",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 1500000),
        ],
    },
    {
        "numero": "3211040",
        "titre": "GESTION DE LA PAIE",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3211044",
        "titre": "TRAITEMENT ET REPROGRAPHIE DES COURRIERS",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 1000000),
        ],
    },
    {
        "numero": "3211047",
        "titre": "FORMATION LONGUE DUREE",
        "lignes": [
            ("6588103", "ALLOCATION FORMATION", 5000000),
            ("6588104", "FRAIS D'INSCRIPTION", 5000000),
        ],
    },
    {
        "numero": "3211051",
        "titre": "KINESITHERAPIE ET REHABILITATION FONCTIONNELLE",
        "lignes": [
            ("2441000", "MATERIELS DE BUREAU", 3200000),
            ("6684000", "PRODUITS PHARMACEUTIQUES", 5000000),
        ],
    },
    {
        "numero": "3211055",
        "titre": "DROITS SOCIAUX DUS AUX EMPLOYES TRANSFERES AU PAK",
        "lignes": [
            ("6614000", "DROITS ET PRIMES SEPARATION", 197921900),
        ],
    },
    {
        "numero": "3212002",
        "titre": "PROGRAMME TRAIN FOR TRADE DE LA CNUCED",
        "lignes": [
            ("6055010", "ACHAT DIRECT FOURNITURES DE BUREAU", 2500000),
            ("6228000", "AUTRES LOCATIONS", 200000),
            ("6271010", "CONCEPTION ET PRODUCTION GADGET", 1200000),
            ("6351100", "COTISATIONS", 17000000),
            ("6383001", "LOCATIONS SERVICES HOTELS", 6000000),
            ("6383100", "RECEPTIONS", 4500000),
            ("6384000", "MISSIONS", 40000000),
            ("6585100", "INDEMNITE DES FORMATEURS INTERNES", 60000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 35000000),
        ],
    },
    {
        "numero": "3212004",
        "titre": "FORMATION DU PERSONNEL PAD",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6330100", "FRAIS DE FORMATION", 60000000),
            ("6585100", "INDEMNITE DES FORMATEURS INTERNES", 120000000),
        ],
    },
    {
        "numero": "3212008",
        "titre": "STAGES ACADEMIQUES ET VACANCES",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6585200", "PECULES DES STAGIAIRES", 33600000),
        ],
    },
    {
        "numero": "3212019",
        "titre": "EVALUATION DES ACTIONS DE FORMATION",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3212022",
        "titre": "EVALUATION DES COMPETENCES DU PERSONNEL DU PAD",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3212031",
        "titre": "MISE EN OEUVRE DU REFERENTIEL METIER COMPETENCE",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6271010", "CONCEPTION ET PRODUCTION GADGET", 1000000),
        ],
    },
    {
        "numero": "3212032",
        "titre": "MISE EN PLACE DE LA GPEC",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3212034",
        "titre": "ORGANISATION DES COACHING, ATELIERS ET SEMINAIRES EN INTERNE",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6266000", "DOCUMENTATION GENERALE ET TECHNIQUE", 1000000),
        ],
    },
    {
        "numero": "3212035",
        "titre": "ANALYSE DES TRAVAUX DE RECHERCHE",
        "lignes": [
            ("6043000", "PRODUITS D'ENTRETIEN SUR STOCK", 100000),
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6588000", "AUTRES CHARGES DIVERSES", 500000),
        ],
    },
    {
        "numero": "3212036",
        "titre": "SUIVI DES APPRENANTS EN FORMATION TRAIN FOR TRADE ET STAGIAIRES PRO",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
        ],
    },
    {
        "numero": "3212038",
        "titre": "CONVENTION DE FORMATION AVEC LE CONSUPE",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 100000),
            ("6330100", "FRAIS DE FORMATION", 25000000),
        ],
    },
    {
        "numero": "3212039",
        "titre": "CONVENTION DE FORMATION AVEC L'ENAM",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 100000),
            ("6330100", "FRAIS DE FORMATION", 25000000),
        ],
    },
    {
        "numero": "3212040",
        "titre": "CONVENTION DE FORMATION AVEC L'ISMP",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 100000),
            ("6330100", "FRAIS DE FORMATION", 20000000),
        ],
    },
    {
        "numero": "3212044",
        "titre": "CONVENTION DE FORMATION AVEC L'ISTA",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 100000),
            ("6330100", "FRAIS DE FORMATION", 25000000),
        ],
    },
    {
        "numero": "3213003",
        "titre": "GESTION SANTE",
        "lignes": [
            ("6055030", "REACTIFS DE LABORATOIRE", 16000000),
            ("6058000", "ACHATS MATERIELS ET EQUIPEMENTS", 9700000),
            ("6272010", "MAGAZINE ET IMPRIME PUBLICITAIRE", 10000000),
            ("6684000", "PRODUITS PHARMACEUTIQUES", 150000000),
            ("6684200", "SOINS ET HOSPITALISATION", 900000000),
            ("6684300", "FRAIS MEDICAUX", 150000000),
        ],
    },
    {
        "numero": "3213004",
        "titre": "MAINTENANCE APPAREILS MEDICAUX",
        "lignes": [
            ("6242102", "MAINTENANCE AUTRES MATERIELS ET ENGINS", 4000000),
        ],
    },
    {
        "numero": "3213006",
        "titre": "EVACUATION SANITAIRE ET RAPATRIEMENT DES DEPOUILLES",
        "lignes": [
            ("6588000", "AUTRES CHARGES DIVERSES", 75000000),
            ("6684200", "SOINS ET HOSPITALISATION", 300000000),
        ],
    },
    {
        "numero": "3213007",
        "titre": "PROMOTION DE LA SANTE",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 200000),
            ("6271010", "CONCEPTION ET PRODUCTION GADGET", 3000000),
            ("6274010", "FOIRES ET EXPOSITIONS", 1000000),
            ("6324130", "HONORAIRES / CONSEILS / COMMISSIONS", 1000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 5000000),
            ("6684000", "PRODUITS PHARMACEUTIQUES", 3000000),
        ],
    },
    {
        "numero": "3213009",
        "titre": "MAINTENANCE ET HYGIENE HOSPITALIERE",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 100000),
            ("6058000", "ACHATS MATERIELS ET EQUIPEMENTS", 8250000),
            ("6588000", "AUTRES CHARGES DIVERSES", 5000000),
        ],
    },
    {
        "numero": "3213010",
        "titre": "LOGISTIQUE HOSPITALIERE",
        "lignes": [
            ("6058000", "ACHATS MATERIELS ET EQUIPEMENTS", 8000000),
        ],
    },
    {
        "numero": "3213011",
        "titre": "SANTE AU TRAVAIL",
        "lignes": [
            ("6324130", "HONORAIRES / CONSEILS / COMMISSIONS", 10000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 2500000),
        ],
    },
    {
        "numero": "3213012",
        "titre": "GESTION DES MENACES ET URGENCES SANITAIRES",
        "lignes": [
            ("6041000", "MATIERES CONSOMMABLES SUR STOCK", 500000),
            ("6248100", "DERATISATION/DESINSECTISATION ET DESINFECTION", 10000000),
        ],
    },
    {
        "numero": "3213013",
        "titre": "EQUIPEMENTS HOSPITALIERS",
        "lignes": [
            ("2488000", "AUTRES MATERIELS ET EQUIPEMENTS", 15000000),
        ],
    },
    {
        "numero": "3213017",
        "titre": "SANTE NUMERIQUE",
        "lignes": [
            ("2488030", "MATERIEL MEDICAL", 342551631),
        ],
    },
    {
        "numero": "3213018",
        "titre": "OPTIMISATION DES COMPETENCES MEDICALES",
        "lignes": [
            ("6277000", "FRAIS DE PARTICIPATION SEMINAIRES", 6000000),
        ],
    },
    {
        "numero": "3214002",
        "titre": "ART, CULTURE ET LOISIRS",
        "lignes": [
            ("6058000", "ACHATS MATERIELS ET EQUIPEMENTS", 8000000),
            ("6228000", "AUTRES LOCATIONS", 2000000),
            ("6383001", "LOCATIONS SERVICES HOTELS", 5000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 5000000),
            ("6684000", "PRODUITS PHARMACEUTIQUES", 400000),
        ],
    },
    {
        "numero": "3214003",
        "titre": "AUTRES ACTIVITES SOCIALES (ARBRE DE NOEL)",
        "lignes": [
            ("6588000", "AUTRES CHARGES DIVERSES", 10000000),
            ("6641100", "AUTRES CHARGES SOCIALES", 90000000),
        ],
    },
    {
        "numero": "3214005",
        "titre": "GESTION DES ACTIVITES SPORTIVES ET CULTURELLES",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 200000),
            ("6058000", "ACHATS MATERIELS ET EQUIPEMENTS", 10000000),
            ("6228000", "AUTRES LOCATIONS", 5000000),
            ("6271010", "CONCEPTION ET PRODUCTION GADGET", 10000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 10000000),
            ("6684000", "PRODUITS PHARMACEUTIQUES", 440000),
        ],
    },
    {
        "numero": "3214006",
        "titre": "RESTAURATION DU PERSONNEL",
        "lignes": [
            ("6688200", "RESTAURATION DU PERSONNEL", 100000000),
        ],
    },
    {
        "numero": "3214009",
        "titre": "ACTIONS SOCIALES",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 200000),
            ("6581111", "DONS", 5000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 3000000),
        ],
    },
    {
        "numero": "3214010",
        "titre": "CELEBRATIONS ET CEREMONIES SOCIALES",
        "lignes": [
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 200000),
            ("6228000", "AUTRES LOCATIONS", 10000000),
            ("6588000", "AUTRES CHARGES DIVERSES", 5000000),
        ],
    },
    {
        "numero": "3215003",
        "titre": "FONCTIONNEMENT COURANT DRH",
        "lignes": [
            ("2441000", "MATERIELS DE BUREAU", 4000000),
            ("2442000", "MATERIELS ET EQUIPEMENTS INFORMATIQUES", 20000000),
            ("6042101", "CARBURANT SUR STOCK", 10380000),
            ("6047210", "FOURNITURES DE BUREAU SUR STOCK", 500000),
            ("6055010", "ACHAT DIRECT FOURNITURES DE BUREAU", 8000000),
            ("6055020", "ACHAT DIRECT CONSOMMABLES INFORMATIQUES", 20000000),
            ("6266000", "DOCUMENTATION GENERALE ET TECHNIQUE", 5000000),
            ("6272010", "MAGAZINE ET IMPRIME PUBLICITAIRE", 4200000),
            ("6330100", "FRAIS DE FORMATION", 25000000),
            ("6384000", "MISSIONS", 40000000),
        ],
    },
    {
        "numero": "3215004",
        "titre": "SALAIRES DRH",
        "lignes": [
            ("6611000", "SALAIRES PERSONNELS", 1468757694),
            ("6641101", "COTISATIONS PATRONNALES", 161563346),
        ],
    },
]

# Virements réels visibles dans le PDF
VIREMENTS_DEMO = [
    # Tâche 3211004 : transfert intra-tâche (6588000 → 6641100)
    ("3211004", "6588000", "3211004", "6641100", 16500000,
     "Transfert interne obsèques : ajustement charges sociales"),
    # Tâche 3211009 : transfert entrant (3211001/6588000 → 3211009/6612500)
    ("3211001", "6588000", "3211009", "6612500", 3319458,
     "Transfert vers distinctions honorifiques"),
]

# Prestataires de démonstration
PRESTATAIRES_DEMO = [
    ("PREST-001", "SARL Papeterie Centrale",  "Rue Njo Njo, Douala",     "+237 233 401 234", "papeterie@example.cm"),
    ("PREST-002", "Clinique Bonanjo",          "Avenue de Gaulle, Douala", "+237 233 421 000", "clinique@example.cm"),
    ("PREST-003", "Tech Solutions SARL",       "Akwa, Douala",             "+237 233 511 200", "tech@example.cm"),
    ("PREST-004", "Bureau Plus",               "Bali, Douala",             "+237 233 601 000", "bureau@example.cm"),
    ("PREST-005", "Groupe Santé PAD",          "Bonanjo, Douala",          "+237 233 701 500", "sante@example.cm"),
]

# Comptes utilisateurs
COMPTES = [
    ("admin",      "pad2025", "admin",          "Dylan Caprel Ngando"),
    ("directeur",  "pad2025", "directeur_drh",  "Marie-Claire Etoa"),
    ("chef",       "pad2025", "chef_service",   "Robert Essomba"),
    ("assistante", "pad2025", "assistante_drh", "Florence Mbarga"),
    ("lecteur",    "pad2025", "lecteur",        "Auditeur Externe"),
]


class Command(BaseCommand):
    help = "Charge les données réelles DRH PAD — Exercice 2026"

    def add_arguments(self, parser):
        parser.add_argument(
            '--flush', action='store_true',
            help='Vide la base avant de charger (ATTENTION : supprime TOUT)',
        )

    def handle(self, *args, **options):
        from core.models import (
            Utilisateur, ExerciceBudgetaire, Tache, LigneBudgetaire,
            VirementBudgetaire, Prestataire, DemandeAchat, Offre,
            BonCommande, LigneBC, ImputationBC, Sequence,
        )

        if options['flush']:
            self.stdout.write(self.style.WARNING("Vidage de la base..."))
            for m in [ImputationBC, VirementBudgetaire, Offre, DemandeAchat, LigneBC,
                      BonCommande, LigneBudgetaire, Tache, Prestataire,
                      ExerciceBudgetaire, Sequence, Utilisateur]:
                m.objects.all().delete()

        with transaction.atomic():
            self._creer_utilisateurs(Utilisateur)
            exercice = self._creer_exercice(ExerciceBudgetaire)
            taches_map, lignes_map = self._creer_taches_lignes(exercice, Tache, LigneBudgetaire)
            self._creer_virements(taches_map, lignes_map, exercice, VirementBudgetaire)
            prests = self._creer_prestataires(Prestataire)
            self._creer_demo_da_bc(
                exercice, taches_map, lignes_map, prests,
                DemandeAchat, Offre, BonCommande, LigneBC, ImputationBC, Sequence, Utilisateur,
            )
            self._creer_sequences(Sequence)

        total = sum(
            sum(Decimal(str(l[2])) for l in t["lignes"])
            for t in TACHES_2026
        )
        self.stdout.write(self.style.SUCCESS(
            f"\nSeed reel PAD 2026 termine :\n"
            f"  - {len(TACHES_2026)} taches\n"
            f"  - {LigneBudgetaire.objects.count()} lignes budgetaires\n"
            f"  - Budget total : {int(total):,} FCFA\n"
            f"  - {Utilisateur.objects.count()} utilisateurs (mdp : pad2025)\n"
            f"  - {Prestataire.objects.count()} prestataires\n"
            f"  - {DemandeAchat.objects.count()} DA / {BonCommande.objects.count()} BC de demo\n"
        ))

    # ── helpers ──────────────────────────────────────────────────────────────

    def _creer_utilisateurs(self, Utilisateur):
        self.stdout.write("  Création des utilisateurs...")
        for username, pwd, role, nom in COMPTES:
            if not Utilisateur.objects.filter(username=username).exists():
                Utilisateur.objects.create_user(
                    username=username, password=pwd,
                    role=role, nom_complet=nom,
                    must_change_password=False,
                )
        # Superuser admin
        if not Utilisateur.objects.filter(username='admin').exists():
            Utilisateur.objects.create_superuser('admin', '', 'pad2025')
        else:
            u = Utilisateur.objects.get(username='admin')
            u.is_staff = True
            u.is_superuser = True
            u.save()

    def _creer_exercice(self, ExerciceBudgetaire):
        self.stdout.write("  Création de l'exercice 2026...")
        total = sum(
            sum(Decimal(str(l[2])) for l in t["lignes"])
            for t in TACHES_2026
        )
        ex, _ = ExerciceBudgetaire.objects.update_or_create(
            annee=2026,
            defaults={
                'date_debut': date(2026, 1, 1),
                'date_fin':   date(2026, 12, 31),
                'montant_global': total,
                'statut': 'actif',
            },
        )
        return ex

    def _creer_taches_lignes(self, exercice, Tache, LigneBudgetaire):
        self.stdout.write(f"  Création de {len(TACHES_2026)} tâches et leurs lignes...")
        taches_map = {}   # numero → Tache
        lignes_map = {}   # (tache_numero, code_nature) → LigneBudgetaire

        for td in TACHES_2026:
            tache, _ = Tache.objects.update_or_create(
                exercice=exercice,
                numero=td["numero"],
                defaults={'titre': td["titre"], 'actif': True},
            )
            taches_map[td["numero"]] = tache

            for code, libelle, montant in td["lignes"]:
                ligne, _ = LigneBudgetaire.objects.update_or_create(
                    tache=tache,
                    code_nature=code,
                    defaults={
                        'libelle_nature': libelle,
                        'montant_initial': Decimal(str(montant)),
                        'actif': True,
                    },
                )
                lignes_map[(td["numero"], code)] = ligne

        return taches_map, lignes_map

    def _creer_virements(self, taches_map, lignes_map, exercice, VirementBudgetaire):
        self.stdout.write("  Création des virements...")
        from core.models import Utilisateur
        admin = Utilisateur.objects.filter(role='admin').first()
        for src_t, src_c, dst_t, dst_c, montant, motif in VIREMENTS_DEMO:
            src_ligne = lignes_map.get((src_t, src_c))
            dst_ligne = lignes_map.get((dst_t, dst_c))
            if src_ligne and dst_ligne:
                VirementBudgetaire.objects.get_or_create(
                    ligne_source=src_ligne,
                    ligne_destination=dst_ligne,
                    montant=Decimal(str(montant)),
                    defaults={
                        'exercice': exercice,
                        'motif': motif,
                        'created_by': admin,
                    },
                )

    def _creer_prestataires(self, Prestataire):
        self.stdout.write("  Création des prestataires...")
        prests = {}
        for code, nom, adresse, tel, email in PRESTATAIRES_DEMO:
            p, _ = Prestataire.objects.update_or_create(
                code=code,
                defaults={'nom': nom, 'adresse': adresse, 'telephone': tel, 'email': email},
            )
            prests[code] = p
        return prests

    def _creer_demo_da_bc(
        self, exercice, taches_map, lignes_map, prests,
        DemandeAchat, Offre, BonCommande, LigneBC, ImputationBC, Sequence, Utilisateur,
    ):
        self.stdout.write("  Création des DA/BC de démonstration...")
        assistante = Utilisateur.objects.filter(role='assistante_drh').first()
        directeur  = Utilisateur.objects.filter(role='directeur_drh').first()

        # Séquences de démo
        seq_da, _ = Sequence.objects.get_or_create(key=f'DA-2026', defaults={'value': 0})
        seq_bc, _ = Sequence.objects.get_or_create(key=f'BC-2026', defaults={'value': 0})

        def next_da():
            from django.db import connection
            seq_da.refresh_from_db()
            seq_da.value += 1
            seq_da.save()
            return f"DA-2026-{seq_da.value:04d}"

        def next_bc():
            seq_bc.refresh_from_db()
            seq_bc.value += 1
            seq_bc.save()
            return f"BC-2026-{seq_bc.value:04d}"

        # === DA 1 : Tâche 3212002 — Programme Train For Trade ===
        tache_tft = taches_map.get("3212002")
        prest1 = prests.get("PREST-001")
        if tache_tft and prest1:
            da1, created = DemandeAchat.objects.get_or_create(
                reference="DA-2026-0001",
                defaults={
                    'exercice': exercice,
                    'tache': tache_tft,
                    'objet': "Fournitures de bureau programme Train For Trade",
                    'montant_estime': Decimal('2500000'),
                    'statut': 'bc_cree',
                    'created_by': assistante,
                },
            )
            if created:
                offre1 = Offre.objects.create(
                    demande=da1, prestataire=prest1,
                    montant=Decimal('2500000'), statut='retenue',
                )
                bc1 = BonCommande.objects.create(
                    numero="BC-2026-0001",
                    demande=da1, tache=tache_tft, exercice=exercice,
                    prestataire=prest1,
                    montant_ht=Decimal('2500000'),
                    montant_tva=Decimal('481250'),
                    montant_ttc=Decimal('2981250'),
                    statut='execute',
                    date_notification=date(2026, 2, 15),
                    delai_execution_jours=30,
                    date_echeance=date(2026, 3, 17),
                )
                ligne_bc1 = LigneBC.objects.create(
                    bon_commande=bc1, designation="Fournitures de bureau",
                    quantite=1, prix_unitaire_ht=Decimal('2500000'), ordre=1,
                )
                ligne_src = lignes_map.get(("3212002", "6055010"))
                if ligne_src:
                    ImputationBC.objects.create(
                        bon_commande=bc1,
                        ligne_budgetaire=ligne_src,
                        montant=Decimal('2500000'),
                        description="Achat direct fournitures de bureau TFT",
                    )
                seq_bc.value = 1; seq_bc.save()
                da1.statut = 'bc_cree'; da1.save()

        # === DA 2 : Gestion Santé (médicaments) ===
        tache_sante = taches_map.get("3213003")
        prest2 = prests.get("PREST-002")
        if tache_sante and prest2:
            da2, created = DemandeAchat.objects.get_or_create(
                reference="DA-2026-0002",
                defaults={
                    'exercice': exercice,
                    'tache': tache_sante,
                    'objet': "Achat médicaments et consommables médicaux",
                    'montant_estime': Decimal('15000000'),
                    'statut': 'validee',
                    'created_by': assistante,
                },
            )
            if created:
                Offre.objects.create(
                    demande=da2, prestataire=prest2,
                    montant=Decimal('14800000'), statut='retenue',
                )

        # === DA 3 : Fonctionnement courant DRH — en étude ===
        tache_fonct = taches_map.get("3215003")
        prest3 = prests.get("PREST-003")
        if tache_fonct and prest3:
            DemandeAchat.objects.get_or_create(
                reference="DA-2026-0003",
                defaults={
                    'exercice': exercice,
                    'tache': tache_fonct,
                    'objet': "Acquisition équipements informatiques DRH",
                    'montant_estime': Decimal('20000000'),
                    'statut': 'en_etude',
                    'created_by': assistante,
                },
            )

        # === BC 2 : Santé — en cours, avec échéance proche ===
        if tache_sante and prest2:
            bc_exists = BonCommande.objects.filter(numero="BC-2026-0002").exists()
            if not bc_exists:
                date_notif = date.today() - timedelta(days=20)
                date_ech   = date.today() + timedelta(days=5)
                bc2 = BonCommande.objects.create(
                    numero="BC-2026-0002",
                    tache=tache_sante, exercice=exercice,
                    prestataire=prest2,
                    montant_ht=Decimal('14800000'),
                    montant_tva=Decimal('2849000'),
                    montant_ttc=Decimal('17649000'),
                    statut='en_cours',
                    date_notification=date_notif,
                    delai_execution_jours=25,
                    date_echeance=date_ech,
                )
                LigneBC.objects.create(
                    bon_commande=bc2, designation="Produits pharmaceutiques",
                    quantite=1, prix_unitaire_ht=Decimal('14800000'), ordre=1,
                )
                ligne_pharma = lignes_map.get(("3213003", "6684000"))
                if ligne_pharma:
                    ImputationBC.objects.create(
                        bon_commande=bc2,
                        ligne_budgetaire=ligne_pharma,
                        montant=Decimal('14800000'),
                        description="Médicaments clinique interne PAD",
                    )

    def _creer_sequences(self, Sequence):
        Sequence.objects.get_or_create(key='DA-2026', defaults={'value': 3})
        Sequence.objects.get_or_create(key='BC-2026', defaults={'value': 2})
        Sequence.objects.get_or_create(key='PREST',   defaults={'value': 5})
