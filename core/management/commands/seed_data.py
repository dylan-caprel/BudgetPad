"""
Seed de demonstration BudgetPAD - DRH du Port Autonome de Douala (PAD)
Exercice 2025 - 120 000 000 FCFA

Lancement : python manage.py seed_data
"""

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone
from decimal import Decimal
from datetime import date, datetime, timedelta
import random

from core.models import (
    Utilisateur, ExerciceBudgetaire, Tache, VirementBudgetaire,
    Prestataire, DemandeAchat, Offre, BonCommande, LigneBC,
    HistoriqueStatut, JournalActivite, Notification, Alerte, Sequence,
)

TVA = Decimal('19.25')


def D(value):
    """Cast rapide en Decimal."""
    return Decimal(str(value))


def aware(d):
    """Convertit une date/datetime en datetime aware."""
    if isinstance(d, datetime):
        dt = d
    else:
        dt = datetime.combine(d, datetime.min.time())
    return timezone.make_aware(dt) if timezone.is_naive(dt) else dt


def force_created_at(obj, dt):
    """Antidate created_at malgre auto_now_add."""
    obj.__class__.objects.filter(pk=obj.pk).update(created_at=aware(dt))


class Command(BaseCommand):
    help = "Genere les donnees de demonstration pour BudgetPAD (DRH du PAD)"

    @transaction.atomic
    def handle(self, *args, **kwargs):
        random.seed(42)  # reproductibilite

        self.stdout.write(self.style.WARNING("=> Purge des donnees..."))
        for m in [Alerte, Notification, JournalActivite, HistoriqueStatut,
                  LigneBC, BonCommande, Offre, DemandeAchat,
                  VirementBudgetaire, Tache, Prestataire, ExerciceBudgetaire,
                  Sequence]:
            m.objects.all().delete()

        users = self._creer_utilisateurs()
        exercice = self._creer_exercice()
        taches = self._creer_taches(exercice)
        self._creer_virements(taches, users)
        prestataires = self._creer_prestataires()
        das = self._creer_demandes_achat(exercice, taches, prestataires, users)
        bcs = self._creer_bons_commande(exercice, taches, prestataires, das, users)
        self._creer_journal(users, taches, das, bcs)
        self._creer_notifications(users, bcs, das)
        self._creer_alertes(taches)
        self._aligner_sequences(taches, das, bcs, prestataires)
        self._sceller_journal()

        self.stdout.write(self.style.SUCCESS("\n=== Seed termine avec succes ==="))
        self._afficher_resume(exercice, taches, bcs, das)

    # ------------------------------------------------------------------ USERS

    def _creer_utilisateurs(self):
        self.stdout.write("=> Utilisateurs...")
        data = [
            ('admin',      'admin@pad.cm',           'admin',          'Dylan Caprel Ngando', True,  True),
            ('directeur',  'directeur.drh@pad.cm',   'directeur_drh',  'Marie-Claire Etoa',   False, False),
            ('assistante', 'assistante.drh@pad.cm',  'assistante_drh', 'Florence Mbarga',     False, False),
            ('dag',        'dag@pad.cm',             'dag',            'Jean-Paul Onana',     False, False),
            ('lecteur',    'audit@pad.cm',           'lecteur',        'Auditeur Externe',    False, False),
        ]
        users = {}
        for username, email, role, nom, is_staff, is_super in data:
            u, _ = Utilisateur.objects.update_or_create(
                username=username,
                defaults={
                    'email': email,
                    'role': role,
                    'nom_complet': nom,
                    'is_staff': is_staff,
                    'is_superuser': is_super,
                    'is_active': True,
                    'must_change_password': True,
                },
            )
            u.set_password('pad2025')
            u.save()
            users[role] = u
        self.stdout.write(f"   {len(users)} utilisateurs (mot de passe : pad2025)")
        return users

    # -------------------------------------------------------------- EXERCICE

    def _creer_exercice(self):
        self.stdout.write("=> Exercice budgetaire...")
        ex = ExerciceBudgetaire.objects.create(
            annee=2025,
            date_debut=date(2025, 1, 1),
            date_fin=date(2025, 12, 31),
            montant_global=D('120000000'),
            statut='actif',
        )
        force_created_at(ex, datetime(2025, 1, 5, 9, 0))
        self.stdout.write("   Exercice 2025 - 120 000 000 FCFA")
        return ex

    # ----------------------------------------------------------------- TACHES

    def _creer_taches(self, exercice):
        """
        15 taches DRH realistes. Budget initial total ~117,5 M FCFA.
        Les taux de consommation sont pilotes par les BCs crees plus loin.
        """
        self.stdout.write("=> Taches budgetaires...")
        data = [
            # (numero, titre, code, libelle_nature, montant_initial)
            ('T-001', "Salaires et primes DRH",              '64110', 'Remunerations personnel',      D('30000000')),
            ('T-002', "Heures supplementaires",              '64130', 'Heures supplementaires',       D('4500000')),
            ('T-003', "Formation continue agents",           '63110', 'Formation',                    D('12000000')),
            ('T-004', "Missions et deplacements",            '62510', 'Missions',                     D('6500000')),
            ('T-005', "Frais medicaux personnel",            '64750', 'Frais medicaux',               D('7500000')),
            ('T-006', "Fournitures de bureau DRH",           '60410', 'Fournitures de bureau',        D('5500000')),
            ('T-007', "Materiel informatique",               '21830', 'Investissement IT',            D('10000000')),
            ('T-008', "Evenements institutionnels",          '62300', 'Communication evenementielle', D('7000000')),
            ('T-009', "Communication interne",               '62310', 'Communication interne',        D('3500000')),
            ('T-010', "Maintenance equipements RH",          '61530', 'Maintenance',                  D('4000000')),
            ('T-011', "Consultants externes RH",             '62280', 'Prestations consultants',      D('9000000')),
            ('T-012', "Transport agents",                    '62410', 'Transport personnel',          D('5500000')),
            ('T-013', "Restauration et evenements sociaux",  '62570', 'Restauration',                 D('4500000')),
            ('T-014', "Medecine du travail",                 '64760', 'Sante au travail',             D('5000000')),
            ('T-015', "Carburant vehicules de service",      '60220', 'Carburants',                   D('3500000')),
        ]
        ts = {}
        for numero, titre, code, lib, montant in data:
            t = Tache.objects.create(
                exercice=exercice,
                numero=numero,
                titre=titre,
                code_nature=code,
                libelle_nature=lib,
                montant_initial=montant,
                taux_previsionnel=D(random.choice([45, 50, 55, 60, 65, 70])),
            )
            force_created_at(t, datetime(2025, 1, 8, 10, 0))
            ts[numero] = t
        total = sum(t.montant_initial for t in ts.values())
        self.stdout.write(f"   15 taches - total initial : {total:,.0f} FCFA")
        return ts

    # --------------------------------------------------------------- VIREMENTS

    def _creer_virements(self, ts, users):
        self.stdout.write("=> Virements inter-taches...")
        virements_data = [
            (date(2025, 2, 12), 'T-009', 'T-003', D('500000'),
             "Reallocation pour formation Excel avancee Q1",                 'assistante_drh'),
            (date(2025, 3, 5),  'T-010', 'T-006', D('300000'),
             "Renforcement fournitures bureau suite a l'audit",              'assistante_drh'),
            (date(2025, 3, 22), 'T-013', 'T-008', D('600000'),
             "Reaffectation pour evenement Journee de la Femme",             'directeur_drh'),
            (date(2025, 4, 10), 'T-005', 'T-014', D('400000'),
             "Couverture medecine du travail - campagne vaccinale",          'assistante_drh'),
            (date(2025, 4, 28), 'T-007', 'T-002', D('250000'),
             "Provision heures supplementaires - pic d'activite portuaire",  'directeur_drh'),
            (date(2025, 5, 14), 'T-001', 'T-011', D('800000'),
             "Mission de conseil organisationnel - cabinet externe",         'assistante_drh'),
        ]
        for dt, src, dst, montant, motif, role in virements_data:
            ts[src].transactions_moins += montant
            ts[src].save(update_fields=['transactions_moins'])
            ts[dst].transactions_plus += montant
            ts[dst].save(update_fields=['transactions_plus'])
            v = VirementBudgetaire.objects.create(
                tache_source=ts[src],
                tache_dest=ts[dst],
                montant=montant,
                motif=motif,
                created_by=users[role],
            )
            force_created_at(v, datetime.combine(dt, datetime.min.time()).replace(hour=10))
        self.stdout.write(f"   {len(virements_data)} virements")

    # ------------------------------------------------------------ PRESTATAIRES

    def _creer_prestataires(self):
        self.stdout.write("=> Prestataires...")
        data = [
            ("Papyrus Afrique SARL",     "Akwa, Douala",            "+237 233 43 11 09", "ventes@papyrus.cm"),
            ("DigitalCare SARL",         "Bonapriso, Douala",       "+237 233 42 30 78", "hello@digitalcare.cm"),
            ("TotalEnergies Cameroun",   "Bonanjo, Douala",         "+237 233 42 99 00", "pro@totalenergies.cm"),
            ("G4S Cameroun",             "Bonaberi, Douala",        "+237 233 47 55 12", "ops@g4s.cm"),
            ("Cleaners Pro SARL",        "Akwa Nord, Douala",       "+237 233 43 88 90", "contact@cleanerspro.cm"),
            ("Cabinet RH Conseil",       "Bonapriso, Douala",       "+237 233 42 15 47", "contact@rhconseil.cm"),
            ("MediPort Sante",           "Bali, Douala",            "+237 233 43 20 65", "info@mediport.cm"),
            ("Voyages Express CM",       "Bonanjo, Douala",         "+237 233 42 78 33", "reservation@vexpress.cm"),
        ]
        ps = {}
        for i, (nom, adr, tel, email) in enumerate(data, 1):
            p = Prestataire.objects.create(
                code=f"PREST-{i:03d}",
                nom=nom,
                adresse=adr,
                telephone=tel,
                email=email,
            )
            force_created_at(p, datetime(2025, 1, 15, 14, 30))
            ps[nom] = p
        self.stdout.write(f"   {len(ps)} prestataires")
        return ps

    # -------------------------------------------------------------------- DA

    def _creer_demandes_achat(self, exercice, ts, ps, users):
        self.stdout.write("=> Demandes d'achat...")
        prest_list = list(ps.values())
        # (date, tache, objet, montant_estime, statut, motif_refus, auteur)
        data = [
            (date(2025, 2, 3),  'T-006', "Fournitures de bureau Q1 - papier, stylos, classeurs",    D('2800000'),  'bc_cree',  '', 'assistante_drh'),
            (date(2025, 2, 18), 'T-003', "Formation Excel avance pour 12 agents",                   D('3500000'),  'bc_cree',  '', 'directeur_drh'),
            (date(2025, 3, 7),  'T-007', "Renouvellement parc PC portables (3 postes)",             D('2800000'),  'validee',  '', 'assistante_drh'),
            (date(2025, 3, 21), 'T-008', "Organisation Journee de la Femme PAD 2025",               D('2800000'),  'bc_cree',  '', 'directeur_drh'),
            (date(2025, 4, 4),  'T-004', "Mission COPIL DRH a Yaounde - 5 agents",                  D('2500000'),  'bc_cree',  '', 'directeur_drh'),
            (date(2025, 4, 12), 'T-002', "Provision heures supplementaires mars-avril 2025",        D('3800000'),  'bc_cree',  '', 'assistante_drh'),
            (date(2025, 4, 19), 'T-011', "Mission consultant organisationnel - 3 mois",             D('2500000'),  'en_etude', '', 'directeur_drh'),
            (date(2025, 5, 2),  'T-015', "Carburant flotte DRH - approvisionnement mai-juin",       D('1500000'),  'validee',  '', 'assistante_drh'),
            (date(2025, 5, 8),  'T-009', "Refonte newsletter interne mensuelle",                    D('800000'),   'refusee',
             "Budget insuffisant en T-009, a representer apres virement.", 'assistante_drh'),
            (date(2025, 5, 14), 'T-014', "Campagne vaccinale agents - grippe saisonniere",          D('3500000'),  'cree',     '', 'assistante_drh'),
        ]
        das = []
        for i, (dt, tnum, objet, montant, statut, motif, role) in enumerate(data, 1):
            ref = f"DA-2025-{i:03d}"
            da = DemandeAchat.objects.create(
                reference=ref,
                exercice=exercice,
                tache=ts[tnum],
                objet=objet,
                montant_estime=montant,
                statut=statut,
                motif_refus=motif,
                created_by=users[role],
            )
            force_created_at(da, datetime.combine(dt, datetime.min.time()).replace(hour=11))
            das.append(da)

            # Offres : 2 a 3 par DA
            nb_offres = 3 if statut in ('bc_cree', 'validee') else 2
            chosen = random.sample(prest_list, nb_offres)
            base = float(montant)
            for idx, prest in enumerate(chosen):
                if statut in ('refusee', 'cree', 'en_etude'):
                    Offre.objects.create(
                        demande=da, prestataire=prest,
                        montant=D(round(base * random.uniform(0.92, 1.10), 0)),
                        statut='refusee',
                        motif_refus=("Demande refusee par le DAG" if statut == 'refusee'
                                     else "Offre en attente de selection"),
                    )
                else:
                    if idx == 0:
                        Offre.objects.create(
                            demande=da, prestataire=prest,
                            montant=D(round(base * random.uniform(0.94, 1.02), 0)),
                            statut='retenue', motif_refus='',
                        )
                    else:
                        Offre.objects.create(
                            demande=da, prestataire=prest,
                            montant=D(round(base * random.uniform(1.03, 1.18), 0)),
                            statut='refusee',
                            motif_refus="Prix superieur a l'offre retenue",
                        )
        self.stdout.write(f"   {len(das)} demandes d'achat + offres")
        return das

    # ------------------------------------------------------------------- BCs

    def _creer_bons_commande(self, exercice, ts, ps, das, users):
        """
        BCs distribues pour atteindre les seuils visuels :
            T-002 : ~94 % (rouge)
            T-006 : ~92 % (rouge)
            T-013 : ~82 % (orange)
            T-014 : ~79 % (orange)
            T-008 : ~76 % (orange)
            T-015 : ~76 % (orange)
            T-004 : ~73 % (orange)
            Autres : < 70 % (vert)
        """
        self.stdout.write("=> Bons de commande...")

        bc_data = [
            # T-006 fournitures - rouge (~92 %)
            (date(2025, 2, 10), 'T-006', "Papyrus Afrique SARL", 'execute',
             [("Mobilier de bureau (armoires, fauteuils)", 1, 1400000),
              ("Toner HP LaserJet pack", 20, 35000),
              ("Ramettes papier A4 80g", 200, 2500),
              ("Fournitures diverses (stylos, agrafes)", 1, 200000)], 0),

            (date(2025, 3, 5), 'T-006', "Papyrus Afrique SARL", 'execute',
             [("Cartouches encre couleur HP", 10, 45000),
              ("Classeurs et reliures A4", 100, 2500),
              ("Tampons et accessoires", 1, 150000),
              ("Archivage et papeterie Q1", 1, 826000)], 0),

            # T-003 formation - vert (~65 %)
            (date(2025, 2, 25), 'T-003', "DigitalCare SARL", 'execute',
             [("Formation Excel avance - 12 agents (5 jours)", 1, 3000000),
              ("Supports pedagogiques + certifications", 12, 41667)], 1),

            (date(2025, 4, 8), 'T-003', "DigitalCare SARL", 'en_cours',
             [("Formation Power BI - 8 agents (3 jours)", 1, 2800000),
              ("Licences Power BI Pro annuelles", 8, 64375)], None),

            # T-007 materiel info - vert (~45 %)
            (date(2025, 3, 12), 'T-007', "DigitalCare SARL", 'notifie',
             [("PC portables HP ProBook 450", 3, 400000),
              ("Sacoches et accessoires", 3, 100000)], 2),

            (date(2025, 4, 2), 'T-007', "DigitalCare SARL", 'execute',
             [("Ecrans 24'' Dell P2422H", 4, 180000),
              ("Stations d'accueil USB-C", 4, 70000)], None),

            (date(2025, 4, 22), 'T-007', "DigitalCare SARL", 'cree',
             [("Imprimante multifonction HP LJ", 1, 980000),
              ("Cartouches toner pack", 2, 100000)], None),

            # T-008 evenements - orange (~76 %)
            (date(2025, 3, 25), 'T-008', "Cleaners Pro SARL", 'execute',
             [("Logistique Journee de la Femme PAD 2025", 1, 1800000),
              ("Decoration et amenagement salle", 1, 650000),
              ("Sonorisation et photographie", 1, 350000)], 3),

            (date(2025, 5, 5), 'T-008', "Cleaners Pro SARL", 'en_cours',
             [("Ceremonie remise medailles du travail", 1, 1200000),
              ("Cocktail dejeunatoire (80 personnes)", 80, 10500)], None),

            # T-004 missions - orange (~73 %)
            (date(2025, 4, 7), 'T-004', "Voyages Express CM", 'execute',
             [("Billets Douala-Yaounde AR (5 agents)", 5, 160000),
              ("Hebergement Yaounde 3 nuits", 15, 65000),
              ("Per diem journalier", 15, 15000)], 4),

            (date(2025, 5, 3), 'T-004', "Voyages Express CM", 'notifie',
             [("Mission audit RH Kribi (3 agents, 4 jours)", 1, 950000),
              ("Location vehicule + carburant", 1, 450000),
              ("Hebergement et indemnites", 1, 579000)], None),

            # T-002 heures supp - rouge (~94 %)
            (date(2025, 4, 18), 'T-002', "Cabinet RH Conseil", 'execute',
             [("Regularisation heures supplementaires Q1 2025", 1, 2500000),
              ("Provision heures supp mars-avril 2025", 1, 1245000)], 5),

            # T-015 carburant - orange (~76 %)
            (date(2025, 5, 6), 'T-015', "TotalEnergies Cameroun", 'en_cours',
             [("Bons carburant Super 91 (1 500 L)", 1500, 560),
              ("Bons carburant Gasoil (600 L)", 600, 600)], 7),

            (date(2025, 3, 18), 'T-015', "TotalEnergies Cameroun", 'execute',
             [("Approvisionnement carburant Q1 DRH", 1, 850000),
              ("Forfait maintenance vehicule", 1, 181000)], None),

            # T-011 consultants - vert (~55 %)
            (date(2025, 5, 15), 'T-011', "Cabinet RH Conseil", 'en_cours',
             [("Mission conseil organisationnel - phase 1", 1, 2200000),
              ("Restitution comite de pilotage", 1, 300000)], 6),

            (date(2025, 3, 28), 'T-011', "Cabinet RH Conseil", 'execute',
             [("Audit conformite SIRH", 1, 1800000),
              ("Rapport et recommandations", 1, 221000)], None),

            # T-005 frais medicaux - vert (~48 %)
            (date(2025, 3, 14), 'T-005', "MediPort Sante", 'execute',
             [("Pharmacie infirmerie Q1", 1, 800000),
              ("Consultations specialistes (8 agents)", 8, 50000)], None),

            (date(2025, 5, 10), 'T-005', "MediPort Sante", 'en_cours',
             [("Bilans sante annuels (40 agents)", 40, 35000),
              ("Tests laboratoire complementaires", 40, 6450)], None),

            # T-013 restauration - orange (~82 %)
            (date(2025, 4, 30), 'T-013', "Cleaners Pro SARL", 'execute',
             [("Service traiteur seminaire DRH (60 pers.)", 60, 18000),
              ("Pauses cafe seminaire (3 jours)", 3, 250000),
              ("Buffet cloture exercice Q1", 1, 852000)], None),

            # T-014 medecine du travail - orange (~79 %)
            (date(2025, 5, 17), 'T-014', "MediPort Sante", 'cree',
             [("Campagne vaccinale grippe (200 doses)", 200, 10000),
              ("Visites medicales periodiques (60 agents)", 60, 14000),
              ("Frais medecin du travail Q2", 1, 738000)], 9),

            # T-009 communication - vert (~55 %)
            (date(2025, 2, 28), 'T-009', "DigitalCare SARL", 'execute',
             [("Refonte charte graphique newsletter", 1, 850000),
              ("Hebergement et licences outils 1 an", 1, 534000)], None),

            # T-010 maintenance - vert (~50 %)
            (date(2025, 3, 8), 'T-010', "Cleaners Pro SARL", 'execute',
             [("Entretien locaux DRH - contrat trimestriel", 3, 450000),
              ("Petites reparations equipements", 1, 201000)], None),

            # T-012 transport - vert (~58 %)
            (date(2025, 4, 14), 'T-012', "Voyages Express CM", 'notifie',
             [("Convention transport agents Douala-Bonaberi", 1, 2200000),
              ("Forfait carburant deplacements internes", 1, 475000)], None),

            # T-001 salaires - vert (~15 %)
            (date(2025, 3, 1), 'T-001', "Cabinet RH Conseil", 'execute',
             [("Regularisation primes de rendement Q1", 1, 2200000),
              ("Indemnites de responsabilite Q1", 1, 1473000)], None),

            # 1 BC annule pour la variete des statuts
            (date(2025, 2, 22), 'T-008', "Cleaners Pro SARL", 'annule',
             [("Cocktail celebration Nouvel An (annule)", 1, 1200000)], None),
        ]

        bcs = []
        for i, (dt, tnum, prest_nom, statut_final, lignes, da_idx) in enumerate(bc_data, 1):
            numero = f"BC-2025-{i:04d}"
            demande = das[da_idx] if da_idx is not None and da_idx < len(das) else None
            tache = ts[tnum]
            prest = ps[prest_nom]

            montant_ht = sum(D(qte) * D(pu) for _, qte, pu in lignes)
            montant_tva = (montant_ht * TVA / 100).quantize(D('0.01'))
            montant_ttc = montant_ht + montant_tva

            bc = BonCommande.objects.create(
                numero=numero,
                demande=demande,
                tache=tache,
                exercice=exercice,
                prestataire=prest,
                direction='Direction des Ressources Humaines',
                taux_tva=TVA,
                montant_ht=montant_ht,
                montant_tva=montant_tva,
                montant_ttc=montant_ttc,
                statut='cree',
            )

            dt_aware = aware(datetime.combine(dt, datetime.min.time()).replace(hour=9, minute=30))
            BonCommande.objects.filter(pk=bc.pk).update(
                date_emission=dt,
                created_at=dt_aware,
            )

            for ordre, (desig, qte, pu) in enumerate(lignes, 1):
                LigneBC.objects.create(
                    bon_commande=bc, designation=desig, quantite=qte,
                    prix_unitaire_ht=D(pu), ordre=ordre,
                )

            chain = self._transition_chain(statut_final)
            current = 'cree'
            for next_statut in chain:
                HistoriqueStatut.objects.create(
                    type_entite='BC', entite_id=bc.id,
                    ancien_statut=current, nouveau_statut=next_statut,
                    utilisateur=users['dag'], commentaire='',
                )
                current = next_statut

            update_fields = {'statut': statut_final}
            if statut_final in ('notifie', 'en_cours', 'execute'):
                update_fields['date_notification'] = dt + timedelta(days=random.randint(2, 5))
            if statut_final == 'annule':
                update_fields['motif_annulation'] = "Annulation suite a reaffectation budgetaire"
            BonCommande.objects.filter(pk=bc.pk).update(**update_fields)

            bcs.append(bc)

        self.stdout.write(f"   {len(bcs)} bons de commande + lignes + historiques")
        return bcs

    @staticmethod
    def _transition_chain(target):
        order = ['cree', 'notifie', 'en_cours', 'execute']
        if target == 'annule':
            return ['annule']
        if target == 'cree':
            return []
        idx = order.index(target)
        return order[1:idx + 1]

    # --------------------------------------------------------------- JOURNAL

    def _creer_journal(self, users, taches, das, bcs):
        self.stdout.write("=> Journal d'activite...")
        admin = users['admin']
        directeur = users['directeur_drh']
        assistante = users['assistante_drh']
        dag = users['dag']

        entries = []

        for i, (numero, t) in enumerate(list(taches.items())[:5]):
            entries.append((
                datetime(2025, 1, 8, 10 + i, 15),
                'Tache.create',
                f"Creation de la tache {t.numero} - {t.titre}",
                'tache', t.id, admin,
            ))

        for i, da in enumerate(das[:6]):
            entries.append((
                datetime(2025, 2 + (i // 3), 5 + i * 3, 11, 0),
                'DA.create',
                f"Creation de {da.reference} - {da.objet}",
                'da', da.id,
                assistante if i % 2 == 0 else directeur,
            ))

        entries.append((datetime(2025, 3, 8, 14, 30),
                        'DA.validate', f"Validation de {das[2].reference}",
                        'da', das[2].id, dag))
        entries.append((datetime(2025, 5, 9, 9, 45),
                        'DA.refuse', f"Refus de {das[8].reference} - budget insuffisant",
                        'da', das[8].id, dag))

        entries.append((datetime(2025, 2, 12, 10, 0),
                        'Virement', "T-009 -> T-003 : 500 000 FCFA",
                        'virement', 1, assistante))
        entries.append((datetime(2025, 4, 28, 10, 0),
                        'Virement', "T-007 -> T-002 : 250 000 FCFA",
                        'virement', 5, directeur))

        for i, bc in enumerate(bcs[:8]):
            entries.append((
                datetime(2025, 2 + (i // 4), 10 + i * 2, 9, 30),
                'BC.create',
                f"Creation du BC {bc.numero}",
                'bc', bc.id, dag,
            ))

        entries.append((datetime(2025, 3, 1, 11, 20),
                        'BC.notify', f"Notification du BC {bcs[0].numero}",
                        'bc', bcs[0].id, dag))
        entries.append((datetime(2025, 3, 15, 16, 0),
                        'BC.execute', f"Execution du BC {bcs[2].numero}",
                        'bc', bcs[2].id, dag))
        entries.append((datetime(2025, 4, 22, 10, 10),
                        'BC.execute', f"Execution du BC {bcs[5].numero}",
                        'bc', bcs[5].id, dag))
        entries.append((datetime(2025, 5, 12, 15, 30),
                        'BC.cancel', f"Annulation du BC {bcs[-1].numero} - reaffectation",
                        'bc', bcs[-1].id, dag))

        for dt, type_action, desc, entite_type, entite_id, user in entries:
            j = JournalActivite.objects.create(
                type_action=type_action,
                description=desc,
                entite_type=entite_type,
                entite_id=entite_id,
                utilisateur=user,
            )
            force_created_at(j, dt)

        self.stdout.write(f"   {len(entries)} entrees de journal")

    # ----------------------------------------------------------- NOTIFICATIONS

    def _creer_notifications(self, users, bcs, das):
        self.stdout.write("=> Notifications...")
        admin = users['admin']
        notifs = [
            ('alerte_seuil', "Tache T-006 critique",
             "La tache T-006 (Fournitures de bureau) depasse 90 % de consommation.",
             'tache', 6),
            ('alerte_seuil', "Tache T-002 critique",
             "La tache T-002 (Heures supplementaires) depasse 90 % de consommation.",
             'tache', 2),
            ('da_validee', "DA-2025-003 validee",
             "La demande d'achat DA-2025-003 (renouvellement parc PC) a ete validee.",
             'da', das[2].id),
            ('bc_execute', f"{bcs[2].numero} execute",
             f"Le BC {bcs[2].numero} a ete marque comme execute.",
             'bc', bcs[2].id),
            ('bc_notifie', f"{bcs[4].numero} notifie",
             f"Le BC {bcs[4].numero} a ete notifie au prestataire.",
             'bc', bcs[4].id),
            ('da_refusee', "DA-2025-009 refusee",
             "La demande DA-2025-009 a ete refusee par le DAG.",
             'da', das[8].id),
            ('virement', "Nouveau virement enregistre",
             "Virement T-007 -> T-002 de 250 000 FCFA enregistre.",
             'virement', 5),
        ]
        for i, (typ, titre, msg, entite_type, entite_id) in enumerate(notifs):
            n = Notification.objects.create(
                utilisateur=admin, type=typ, titre=titre, message=msg,
                entite_type=entite_type, entite_id=entite_id, lu=False,
            )
            force_created_at(n, datetime(2025, 5, 10 + i, 9, 0))
        self.stdout.write(f"   {len(notifs)} notifications non lues")

    # ----------------------------------------------------------------- ALERTES

    def _creer_alertes(self, ts):
        self.stdout.write("=> Alertes budgetaires...")
        nb = 0
        for tache in ts.values():
            tache.refresh_from_db()
            taux = float(tache.taux_consommation)
            if taux >= 80:
                Alerte.objects.create(
                    tache=tache,
                    type_alerte='seuil_atteint',
                    message=f"{tache.numero} {tache.titre} - taux {taux:.1f} %",
                    seuil_atteint=D(round(taux, 2)),
                    lu=False,
                )
                nb += 1
        self.stdout.write(f"   {nb} alertes generees (taux >= 80 %)")

    # -------------------------------------------------------------- SEQUENCES

    def _aligner_sequences(self, taches, das, bcs, ps):
        self.stdout.write("=> Alignement des sequences...")
        Sequence.objects.update_or_create(key='BC-2025',  defaults={'value': len(bcs)})
        Sequence.objects.update_or_create(key='DA-2025',  defaults={'value': len(das)})
        Sequence.objects.update_or_create(key='T-2025',   defaults={'value': len(taches)})
        Sequence.objects.update_or_create(key='PREST',    defaults={'value': len(ps)})
        self.stdout.write("   Compteurs : BC-2025, DA-2025, T-2025, PREST")

    # -------------------------------------------------------------- SIGNATURE

    def _sceller_journal(self):
        self.stdout.write("=> Scellement chaine de hash JournalActivite...")
        from django.core.management import call_command
        call_command('rebuild_audit_chain', '--confirm', verbosity=0)
        self.stdout.write("   Chaine reconstruite.")

    # ---------------------------------------------------------------- RESUME

    def _afficher_resume(self, exercice, ts, bcs, das):
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(
            f"Exercice {exercice.annee} - {exercice.montant_global:,.0f} FCFA"
        ))
        self.stdout.write(f"  Taches            : {len(ts)}")
        self.stdout.write(f"  Demandes d'achat  : {len(das)}")
        self.stdout.write(f"  Bons de commande  : {len(bcs)}")
        self.stdout.write("")
        self.stdout.write("Comptes (mot de passe : pad2025):")
        self.stdout.write("  admin      / Administrateur")
        self.stdout.write("  directeur  / Directeur DRH")
        self.stdout.write("  assistante / Assistante DRH")
        self.stdout.write("  dag        / DAG (validateur)")
        self.stdout.write("  lecteur    / Auditeur Externe")
        self.stdout.write("")
        self.stdout.write("Acces : http://127.0.0.1:8000/login/")
