from django.db import models
from django.db.models import (
    Case, DecimalField, ExpressionWrapper, F, OuterRef, Q, Subquery, Sum, Value, When,
)
from django.db.models.functions import Coalesce
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.core.exceptions import ValidationError
from decimal import Decimal
from datetime import date, timedelta


# ─────────────────────────────────────────────────────────────
# UTILISATEUR
# ─────────────────────────────────────────────────────────────

class Utilisateur(AbstractUser):
    ROLE_CHOICES = [
        ('admin',          'Administrateur'),
        ('directeur_drh',  'Directeur DRH'),
        ('chef_service',   'Chef de service'),
        ('assistante_drh', 'Assistante DRH'),
        ('lecteur',        'Lecteur'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='lecteur')
    nom_complet = models.CharField(max_length=150, blank=True)
    must_change_password = models.BooleanField(
        default=False,
        help_text="Si vrai, l'utilisateur est forcé de changer son mot de passe à la prochaine connexion.",
    )

    def __str__(self):
        return self.nom_complet or self.username

    def get_role_display_short(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)


# ─────────────────────────────────────────────────────────────
# EXERCICE BUDGÉTAIRE
# ─────────────────────────────────────────────────────────────

class ExerciceBudgetaire(models.Model):
    annee = models.IntegerField(unique=True)
    date_debut = models.DateField()
    date_fin = models.DateField()
    montant_global = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    STATUT_CHOICES = [('actif', 'Actif'), ('cloture', 'Clôturé')]
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='actif')
    # Règle R7 : is_active garantit qu'un seul exercice est actif à la fois
    is_active = models.BooleanField(
        default=False,
        help_text="Exercice courant — un seul peut être actif (Règle R7).",
    )
    is_locked = models.BooleanField(
        default=False,
        help_text="Si vrai, l'exercice est en lecture seule — aucune création/modification autorisée.",
    )
    seuil_alerte = models.PositiveSmallIntegerField(
        default=80,
        help_text="Seuil de taux de consommation (en %) déclenchant une alerte sur une tâche.",
    )
    exercice_precedent = models.ForeignKey(
        'self', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='exercices_suivants',
        help_text="Exercice de l'année précédente (renseigné automatiquement).",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-annee']
        verbose_name = 'Exercice budgétaire'
        verbose_name_plural = 'Exercices budgétaires'

    def __str__(self):
        if self.is_active:
            statut = 'ACTIF'
        elif self.is_locked:
            statut = 'CLÔTURÉ'
        else:
            statut = 'Inactif'
        return f"Exercice {self.annee} [{statut}]"

    @classmethod
    def get_actif(cls):
        """Retourne l'exercice actif ou None. Priorité : is_active, puis statut='actif'."""
        return (
            cls.objects.filter(is_active=True).first()
            or cls.objects.filter(statut='actif').first()
        )

    def activer(self, user=None):
        """Active cet exercice. RÈGLE R7 : désactive automatiquement tous les autres.

        Protégé contre les race conditions par un select_for_update atomique.
        """
        from django.db import transaction
        if self.is_locked:
            raise ValueError(f"L'exercice {self.annee} est clôturé, impossible de l'activer.")
        with transaction.atomic():
            # Lock toutes les lignes pour empêcher une activation concurrente
            list(ExerciceBudgetaire.objects.select_for_update().all())
            ExerciceBudgetaire.objects.exclude(pk=self.pk).update(is_active=False)
            self.is_active = True
            self.statut = 'actif'
            self.save(update_fields=['is_active', 'statut'])
        JournalActivite.objects.create(
            type_action='Exercice.activer',
            description=(
                f"Exercice {self.annee} activé — Règle R7 appliquée : "
                f"tous les autres exercices ont été désactivés."
            ),
            entite_type='ExerciceBudgetaire',
            entite_id=self.pk,
            utilisateur=user,
        )

    def cloturer(self, user=None):
        """Clôture l'exercice (lecture seule définitive)."""
        from django.db import transaction
        with transaction.atomic():
            self.is_active = False
            self.is_locked = True
            self.statut = 'cloture'
            self.save(update_fields=['is_active', 'is_locked', 'statut'])
        JournalActivite.objects.create(
            type_action='Exercice.cloture',
            description=f"Exercice {self.annee} clôturé définitivement.",
            entite_type='ExerciceBudgetaire',
            entite_id=self.pk,
            utilisateur=user,
        )

    def save(self, *args, **kwargs):
        # COHE-1 : synchronise les deux sources de vérité statut/is_active
        if self.is_locked:
            self.statut = 'cloture'
            self.is_active = False
        elif self.is_active and self.statut != 'actif':
            self.statut = 'actif'
        super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# TACHE + LigneBudgetaire
# ─────────────────────────────────────────────────────────────

def _sum_subquery(queryset, group_field, sum_field):
    """Agrégat SUM isolé dans une sous-requête corrélée (OuterRef).

    Évite le piège Django du produit cartésien : additionner plusieurs relations
    multi-valuées dans la MÊME requête via des JOIN multiplie les lignes et fausse
    chaque Sum dès qu'une entité porte ≥ 2 lignes liées (2 BC, 2 virements…).
    En isolant chaque agrégat dans son propre SELECT, aucun JOIN ne se croise.

    `queryset` doit déjà être filtré via OuterRef pour ne viser que l'entité courante.
    Renvoie ``Coalesce(Subquery(SUM(sum_field) GROUP BY group_field), 0)``.
    """
    df = DecimalField(max_digits=15, decimal_places=2)
    return Coalesce(
        Subquery(
            queryset.values(group_field).annotate(_total=Sum(sum_field)).values('_total'),
            output_field=df,
        ),
        Value(Decimal('0'), output_field=df),
    )


class TacheQuerySet(models.QuerySet):
    def with_aggregates(self):
        df = DecimalField(max_digits=15, decimal_places=2)
        zero = Value(Decimal('0'), output_field=df)
        return (
            self
            .annotate(
                # Budget initial : somme des lignes actives de la tâche.
                total_budget_initial=_sum_subquery(
                    LigneBudgetaire.objects.filter(tache=OuterRef('pk'), actif=True),
                    'tache', 'montant_initial',
                ),
                # Transferts entrants : virements dont la ligne destination est une
                # ligne active de la tâche.
                total_transfert_plus=_sum_subquery(
                    VirementBudgetaire.objects.filter(
                        ligne_destination__tache=OuterRef('pk'),
                        ligne_destination__actif=True,
                    ),
                    'ligne_destination__tache', 'montant',
                ),
                # Transferts sortants : virements dont la ligne source est une ligne
                # active de la tâche.
                total_transfert_moins=_sum_subquery(
                    VirementBudgetaire.objects.filter(
                        ligne_source__tache=OuterRef('pk'),
                        ligne_source__actif=True,
                    ),
                    'ligne_source__tache', 'montant',
                ),
            )
            .annotate(
                total_budget_ajuste=ExpressionWrapper(
                    F('total_budget_initial') + F('total_transfert_plus') - F('total_transfert_moins'),
                    output_field=df,
                ),
            )
            .annotate(
                # Conso BC : imputations des lignes actives, hors BC annulés.
                total_conso_bc=_sum_subquery(
                    ImputationBC.objects
                    .filter(ligne_budgetaire__tache=OuterRef('pk'), ligne_budgetaire__actif=True)
                    .exclude(bon_commande__statut='annule'),
                    'ligne_budgetaire__tache', 'montant',
                ),
            )
            .annotate(
                # Conso directe : consommations des lignes actives, hors annulées.
                total_conso_directe=_sum_subquery(
                    ConsommationDirecte.objects.filter(
                        ligne_budgetaire__tache=OuterRef('pk'),
                        ligne_budgetaire__actif=True,
                        est_annule=False,
                    ),
                    'ligne_budgetaire__tache', 'montant',
                ),
            )
            .annotate(
                total_consommation=ExpressionWrapper(
                    F('total_conso_bc') + F('total_conso_directe'),
                    output_field=df,
                ),
            )
            .annotate(
                total_solde=ExpressionWrapper(
                    F('total_budget_ajuste') - F('total_consommation'),
                    output_field=df,
                ),
                taux_consommation_global=Case(
                    When(total_budget_ajuste=0, then=zero),
                    default=ExpressionWrapper(
                        F('total_consommation') * 100 / F('total_budget_ajuste'),
                        output_field=df,
                    ),
                ),
            )
        )


class TacheManager(models.Manager.from_queryset(TacheQuerySet)):
    pass


class Tache(models.Model):
    exercice = models.ForeignKey(
        'ExerciceBudgetaire', on_delete=models.CASCADE, related_name='taches',
    )
    numero = models.CharField(max_length=20)
    titre = models.CharField(max_length=500)
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TacheManager()

    class Meta:
        ordering = ['numero']
        unique_together = ['exercice', 'numero']
        verbose_name = 'Tâche budgétaire'
        verbose_name_plural = 'Tâches budgétaires'

    def __str__(self):
        return f"{self.numero} — {self.titre}"

    # ── agrégats (utilisés avec .with_aggregates()) ──

    @property
    def budget_initial(self):
        if hasattr(self, 'total_budget_initial') and self.total_budget_initial is not None:
            return self.total_budget_initial
        return self.lignes.filter(actif=True).aggregate(t=Sum('montant_initial'))['t'] or Decimal('0')

    @property
    def budget_ajuste(self):
        if hasattr(self, 'total_budget_ajuste') and self.total_budget_ajuste is not None:
            return self.total_budget_ajuste
        lines = self.lignes.filter(actif=True)
        bi = lines.aggregate(t=Sum('montant_initial'))['t'] or Decimal('0')
        tp = lines.aggregate(t=Sum('virements_entrants__montant'))['t'] or Decimal('0')
        tm = lines.aggregate(t=Sum('virements_sortants__montant'))['t'] or Decimal('0')
        return bi + tp - tm

    @property
    def consommation(self):
        if hasattr(self, 'total_consommation') and self.total_consommation is not None:
            return self.total_consommation
        return Decimal('0')

    @property
    def solde(self):
        if hasattr(self, 'total_solde') and self.total_solde is not None:
            return self.total_solde
        return self.budget_ajuste - self.consommation

    @property
    def taux_consommation(self):
        if hasattr(self, 'taux_consommation_global') and self.taux_consommation_global is not None:
            return self.taux_consommation_global
        ba = self.budget_ajuste
        if ba and ba > 0:
            return round((self.consommation / ba) * 100, 1)
        return Decimal('0')

    @property
    def taux_couleur(self):
        taux = float(self.taux_consommation)
        if taux >= 90:
            return 'danger'
        if taux >= 70:
            return 'warning'
        return 'success'


# ─────────────────────────────────────────────────────────────
# LIGNE BUDGÉTAIRE
# ─────────────────────────────────────────────────────────────

class LigneBudgetaireQuerySet(models.QuerySet):
    def with_aggregates(self):
        df = DecimalField(max_digits=15, decimal_places=2)
        zero = Value(Decimal('0'), output_field=df)
        return (
            self
            .annotate(
                # Chaque agrégat est isolé dans sa propre sous-requête : additionner
                # virements + imputations + consommations dans la même requête via des
                # JOIN multiplierait les lignes (produit cartésien) dès qu'une ligne
                # porte ≥ 2 entités liées, faussant tous les Sum.
                transfert_plus=_sum_subquery(
                    VirementBudgetaire.objects.filter(ligne_destination=OuterRef('pk')),
                    'ligne_destination', 'montant',
                ),
                transfert_moins=_sum_subquery(
                    VirementBudgetaire.objects.filter(ligne_source=OuterRef('pk')),
                    'ligne_source', 'montant',
                ),
            )
            .annotate(
                budget_ajuste=ExpressionWrapper(
                    F('montant_initial') + F('transfert_plus') - F('transfert_moins'),
                    output_field=df,
                ),
            )
            .annotate(
                consommation_bc=_sum_subquery(
                    ImputationBC.objects
                    .filter(ligne_budgetaire=OuterRef('pk'))
                    .exclude(bon_commande__statut='annule'),
                    'ligne_budgetaire', 'montant',
                ),
            )
            .annotate(
                consommation_directe=_sum_subquery(
                    ConsommationDirecte.objects.filter(
                        ligne_budgetaire=OuterRef('pk'), est_annule=False,
                    ),
                    'ligne_budgetaire', 'montant',
                ),
            )
            .annotate(
                consommation=ExpressionWrapper(
                    F('consommation_bc') + F('consommation_directe'),
                    output_field=df,
                ),
            )
            .annotate(
                solde=ExpressionWrapper(F('budget_ajuste') - F('consommation'), output_field=df),
                taux_consommation=Case(
                    When(budget_ajuste=0, then=zero),
                    default=ExpressionWrapper(
                        F('consommation') * 100 / F('budget_ajuste'), output_field=df,
                    ),
                ),
            )
        )


class LigneBudgetaireManager(models.Manager.from_queryset(LigneBudgetaireQuerySet)):
    pass


class LigneBudgetaire(models.Model):
    tache = models.ForeignKey(Tache, on_delete=models.CASCADE, related_name='lignes')
    code_nature = models.CharField(max_length=10)
    libelle_nature = models.CharField(max_length=255)
    montant_initial = models.DecimalField(
        max_digits=15, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal('0'))],
    )
    actif = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = LigneBudgetaireManager()

    class Meta:
        ordering = ['code_nature']
        verbose_name = 'Ligne budgétaire'
        verbose_name_plural = 'Lignes budgétaires'

    def __str__(self):
        return f"{self.code_nature} — {self.libelle_nature}"


# ─────────────────────────────────────────────────────────────
# VIREMENT BUDGÉTAIRE (entre lignes)
# ─────────────────────────────────────────────────────────────

class VirementBudgetaire(models.Model):
    exercice = models.ForeignKey(
        'ExerciceBudgetaire', on_delete=models.CASCADE, related_name='virements',
    )
    ligne_source = models.ForeignKey(
        LigneBudgetaire, on_delete=models.PROTECT, related_name='virements_sortants',
    )
    ligne_destination = models.ForeignKey(
        LigneBudgetaire, on_delete=models.PROTECT, related_name='virements_entrants',
    )
    montant = models.DecimalField(
        max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))],
    )
    motif = models.TextField()
    created_by = models.ForeignKey('Utilisateur', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Virement budgétaire'
        verbose_name_plural = 'Virements budgétaires'

    def clean(self):
        if self.ligne_source_id and self.ligne_destination_id:
            if self.ligne_source_id == self.ligne_destination_id:
                raise ValidationError("La ligne source et destination doivent être différentes.")
        if self.montant and self.montant <= 0:
            raise ValidationError("Le montant doit être positif.")

    def __str__(self):
        src = self.ligne_source.code_nature if self.ligne_source_id else '?'
        dst = self.ligne_destination.code_nature if self.ligne_destination_id else '?'
        return f"{src} → {dst} : {self.montant:,.0f} FCFA"


# ─────────────────────────────────────────────────────────────
# PRESTATAIRE
# ─────────────────────────────────────────────────────────────

class Prestataire(models.Model):
    code = models.CharField(max_length=20, unique=True)
    nom = models.CharField(max_length=150)
    adresse = models.TextField(blank=True)
    telephone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.nom}"


# ─────────────────────────────────────────────────────────────
# DEMANDE D'ACHAT
# ─────────────────────────────────────────────────────────────

class DemandeAchat(models.Model):
    STATUT_CHOICES = [
        ('cree',     'Créée'),
        ('en_etude', 'Transmise DAG'),
        ('validee',  'Validée'),
        ('bc_cree',  'BC créé'),
        ('annulee',  'Annulée'),
    ]
    reference = models.CharField(
        max_length=30, unique=True, blank=True,
        help_text="Laisser vide pour auto-génération au format DAC{AAMM}DLA{NNNNN}",
    )
    exercice = models.ForeignKey(
        ExerciceBudgetaire, on_delete=models.CASCADE, related_name='demandes_achat',
    )
    # Correction encadreur : DA liée à la ligne budgétaire (pas à la tâche)
    ligne_budgetaire = models.ForeignKey(
        'LigneBudgetaire', on_delete=models.PROTECT,
        related_name='demandes_achat', null=True, blank=True,
        verbose_name="Ligne budgétaire concernée",
    )
    objet = models.CharField(max_length=200)
    montant_estime = models.DecimalField(max_digits=15, decimal_places=2)
    # ── Champs conformité format réel PAD (tableau engagements DRH) ──
    nature_prestation = models.CharField(
        max_length=20, blank=True,
        choices=[
            ('APPRO', 'Approvisionnement (APPRO)'),
            ('Trx', 'Travaux (Trx)'),
            ('Prestat.Int', 'Prestation intellectuelle (Prestat.Int)'),
            ('Autre', 'Autre'),
        ],
        verbose_name="Nature de la prestation",
    )
    periode_engagement = models.CharField(
        max_length=5, blank=True,
        choices=[
            ('P1', 'Période 1 (Mars — Juin)'),
            ('P2', 'Période 2 (Juillet — Novembre)'),
        ],
        verbose_name="Période d'engagement",
    )
    priorite = models.CharField(
        max_length=2, blank=True,
        choices=[('1', 'Priorité 1'), ('2', 'Priorité 2')],
        verbose_name="Priorité",
    )
    statut = models.CharField(max_length=15, choices=STATUT_CHOICES, default='cree')
    motif_refus = models.TextField(blank=True, verbose_name="Motif d'annulation")
    created_by = models.ForeignKey('Utilisateur', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Demande d'achat"
        verbose_name_plural = "Demandes d'achat"
        # REFACTOR: index sur les filtres les plus fréquents (da_list, workflow DA→BC)
        indexes = [
            models.Index(fields=['exercice', 'statut'], name='idx_da_exercice_statut'),
            models.Index(fields=['statut'], name='idx_da_statut'),
        ]

    def __str__(self):
        return f"{self.reference} — {self.objet}"

    def save(self, *args, **kwargs):
        # Auto-génération de la référence au format réel PAD : DAC{AAMM}DLA{NNNNN}
        if not self.reference:
            from .services.sequence_service import SequenceService
            self.reference = SequenceService.next_da_reference()
        super().save(*args, **kwargs)

    # ── Propriétés dérivées depuis la ligne budgétaire ──

    @property
    def tache(self):
        if self.ligne_budgetaire_id:
            return self.ligne_budgetaire.tache
        return None

    # ── Couleur statut ──

    @property
    def statut_couleur(self):
        return {
            'cree': 'secondary', 'en_etude': 'warning', 'validee': 'success',
            'bc_cree': 'info', 'annulee': 'danger',
        }.get(self.statut, 'secondary')

    TRANSITIONS_AUTORISEES = {
        'cree':     ['en_etude', 'annulee'],
        'en_etude': ['validee', 'annulee'],
        'validee':  ['bc_cree'],
        'bc_cree':  [],
        'annulee':  [],
    }

    def peut_transiter_vers(self, nouveau_statut):
        autorisees = self.TRANSITIONS_AUTORISEES.get(self.statut, [])
        if nouveau_statut not in autorisees:
            return False, f"Transition « {self.get_statut_display()} » → « {nouveau_statut} » interdite."
        if nouveau_statut == 'validee':
            offres_recues   = self.offres.filter(statut__in=['recue', 'retenue']).count()
            offres_retenues = self.offres.filter(statut='retenue').count()
            if offres_recues == 0:
                return False, "Aucune offre reçue — impossible de valider la DA."
            if offres_retenues != 1:
                return False, "Exactement 1 offre doit être retenue avant la validation."
            pj_valides = PieceJointe.objects.filter(
                type_entite='da', entite_id=self.pk,
                type_piece__in=['facture_proforma', 'da_signee'],
            ).exists()
            if not pj_valides:
                return False, (
                    "Joignez au moins une facture proforma ou la DA signée "
                    "avant de valider cette demande."
                )
        if nouveau_statut == 'annulee' and not self.motif_refus:
            return False, "Motif d'annulation obligatoire."
        return True, "OK"


# ─────────────────────────────────────────────────────────────
# OFFRE
# ─────────────────────────────────────────────────────────────

class Offre(models.Model):
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('recue',      'Reçue'),
        ('retenue',    'Retenue'),
        ('refusee',    'Refusée'),
    ]
    demande            = models.ForeignKey(DemandeAchat, on_delete=models.CASCADE, related_name='offres')
    prestataire        = models.ForeignKey(Prestataire, on_delete=models.CASCADE)
    montant            = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    statut             = models.CharField(max_length=10, choices=STATUT_CHOICES, default='en_attente')
    motif_refus        = models.TextField(blank=True)
    date_sollicitation = models.DateTimeField(auto_now_add=True)
    date_reception     = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['date_sollicitation']
        verbose_name = 'Offre prestataire'

    def __str__(self):
        montant_str = f"{self.montant:,.0f} FCFA" if self.montant is not None else "—"
        return f"Offre {self.prestataire.nom} — {montant_str}"

    @property
    def est_en_retard(self):
        if self.statut != 'en_attente':
            return False
        from django.utils import timezone
        return (timezone.now() - self.date_sollicitation).days > 7

    @property
    def statut_couleur(self):
        return {
            'en_attente': 'warning', 'recue': 'info',
            'retenue': 'success', 'refusee': 'secondary',
        }.get(self.statut, 'secondary')

    @property
    def statut_icon(self):
        return {
            'en_attente': 'hourglass-split', 'recue': 'envelope-check',
            'retenue': 'trophy', 'refusee': 'x-circle',
        }.get(self.statut, 'circle')

    TRANSITIONS_AUTORISEES = {
        'en_attente': ['recue'],
        'recue':      ['retenue', 'refusee'],
        'retenue':    [],
        'refusee':    [],
    }

    def peut_transiter_vers(self, nouveau_statut):
        autorisees = self.TRANSITIONS_AUTORISEES.get(self.statut, [])
        if nouveau_statut not in autorisees:
            return False, f"Transition « {self.get_statut_display()} » → « {nouveau_statut} » interdite."
        if nouveau_statut == 'retenue':
            deja_retenue = self.demande.offres.filter(statut='retenue').exclude(pk=self.pk).exists()
            if deja_retenue:
                return False, "Une offre est déjà retenue pour cette DA — une seule retenue autorisée."
        return True, "OK"


# ─────────────────────────────────────────────────────────────
# BON DE COMMANDE
# ─────────────────────────────────────────────────────────────

class BonCommande(models.Model):
    STATUT_CHOICES = [
        ('cree',     'Créé'),
        ('notifie',  'Notifié'),
        ('en_cours', 'En cours'),
        ('execute',  'Exécuté'),
        ('annule',   'Annulé'),
    ]
    TRANSITIONS = {
        'cree':     ['notifie', 'annule'],
        'notifie':  ['en_cours', 'annule'],
        'en_cours': ['execute', 'annule'],
        'execute':  [],
        'annule':   [],
    }
    numero           = models.CharField(
        max_length=30, unique=True, blank=True,
        help_text="Laisser vide pour auto-génération au format STD{AAMM}DLA{NNNNN}",
    )
    demande          = models.ForeignKey(
        DemandeAchat, on_delete=models.PROTECT, related_name='bons_commande',
        null=True, blank=True,
    )
    tache            = models.ForeignKey(Tache, on_delete=models.CASCADE, related_name='bons_commande')
    exercice         = models.ForeignKey(
        ExerciceBudgetaire, on_delete=models.CASCADE, related_name='bons_commande',
    )
    prestataire      = models.ForeignKey(
        Prestataire, on_delete=models.PROTECT, related_name='bons_commande',
    )
    direction        = models.CharField(max_length=100, default='Direction des Ressources Humaines')
    # ── Avis CAPRI (Règle R11 : toute imputation requiert un avis CAPRI préalable de la DCG) ──
    numero_capri     = models.CharField(
        max_length=50, blank=True, verbose_name="Numéro CAPRI",
        help_text="Numéro de l'avis CAPRI qui autorise cette imputation",
    )
    date_capri       = models.DateField(
        null=True, blank=True, verbose_name="Date d'émission CAPRI",
    )
    date_emission    = models.DateField(auto_now_add=True)
    date_notification = models.DateField(null=True, blank=True)
    delai_execution_jours = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Délai accordé au prestataire pour l'exécution (en jours) — legacy",
    )
    delai_execution_semaines = models.PositiveIntegerField(
        null=True, blank=True,
        verbose_name="Délai d'exécution (semaines)",
        help_text="Ex: 4 pour 4 semaines. La date d'échéance est calculée automatiquement.",
    )
    date_echeance    = models.DateField(null=True, blank=True)
    condition_paiement = models.CharField(
        max_length=100, default='virement_60',
        choices=[
            ('virement_60', 'Virement 60 jours fin de mois'),
            ('virement_30', 'Virement 30 jours fin de mois'),
            ('comptant', 'Paiement comptant'),
            ('autre', 'Autre'),
        ],
        verbose_name="Condition de paiement",
    )
    rib_paiement     = models.CharField(
        max_length=50, blank=True, verbose_name="RIB de paiement",
        help_text="Ex: 10003 03900 06000053467 94",
    )
    objet            = models.TextField(blank=True, verbose_name="Objet du bon de commande")
    taux_tva         = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('19.25'))
    montant_ht       = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_tva      = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_ttc      = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statut           = models.CharField(
        max_length=10, choices=STATUT_CHOICES, default='cree', db_index=True,
    )
    motif_annulation = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Bon de commande'
        verbose_name_plural = 'Bons de commande'
        indexes = [
            models.Index(fields=['exercice', 'statut', '-created_at']),
            models.Index(fields=['tache', 'statut']),
            models.Index(fields=['prestataire', '-created_at']),
            models.Index(fields=['statut']),
            # REFACTOR: filtres de période (bilans) et requêtes d'échéance (dashboard)
            models.Index(fields=['date_emission'], name='idx_bc_date_emission'),
            models.Index(fields=['date_echeance'], name='idx_bc_date_echeance'),
        ]

    def __str__(self):
        return f"{self.numero} — {self.prestataire.nom}"

    def save(self, *args, **kwargs):
        # Auto-génération du numéro au format réel PAD : STD{AAMM}DLA{NNNNN}
        if not self.numero:
            from .services.sequence_service import SequenceService
            self.numero = SequenceService.next_bc_numero()
        # Échéance auto : priorité au délai en semaines, sinon legacy jours
        if self.date_notification:
            if self.delai_execution_semaines:
                self.date_echeance = self.date_notification + timedelta(weeks=self.delai_execution_semaines)
            elif self.delai_execution_jours:
                self.date_echeance = self.date_notification + timedelta(days=self.delai_execution_jours)
        super().save(*args, **kwargs)

    @property
    def statut_couleur(self):
        return {
            'cree': 'secondary', 'notifie': 'info', 'en_cours': 'primary',
            'execute': 'success', 'annule': 'danger',
        }.get(self.statut, 'secondary')

    @property
    def est_en_retard(self):
        return bool(self.date_echeance and self.statut == 'en_cours' and date.today() > self.date_echeance)

    @property
    def jours_restants(self):
        if self.date_echeance and self.statut in ('notifie', 'en_cours'):
            return (self.date_echeance - date.today()).days
        return None

    @property
    def echeance_proche(self):
        jr = self.jours_restants
        return jr is not None and 0 < jr <= 7

    @property
    def delai_affichage(self):
        """Affichage humain du délai (priorité aux semaines, format réel PAD)."""
        if self.delai_execution_semaines:
            return f"{self.delai_execution_semaines:02d} semaines"
        if self.delai_execution_jours:
            return f"{self.delai_execution_jours} jours"
        return "—"

    @property
    def capri_manquant(self):
        """True si l'avis CAPRI (n° + date) n'est pas renseigné — à régulariser (R11)."""
        return not (self.numero_capri and self.date_capri)

    def recalculer_montants(self):
        """Recalcule HT/TVA/TTC depuis les lignes d'articles et sauvegarde."""
        self.calculer_montants()
        self.save(update_fields=['montant_ht', 'montant_tva', 'montant_ttc'])

    def peut_transiter(self, nouveau_statut):
        return nouveau_statut in self.TRANSITIONS.get(self.statut, [])

    def peut_transiter_vers(self, nouveau_statut):
        if nouveau_statut not in self.TRANSITIONS.get(self.statut, []):
            return False, f"Transition « {self.get_statut_display()} » → « {nouveau_statut} » interdite."
        if nouveau_statut == 'notifie':
            has_pj = PieceJointe.objects.filter(
                type_entite='bc', entite_id=self.pk, type_piece='bon_commande',
            ).exists()
            if not has_pj:
                return False, (
                    "Un bon de commande signé (pièce jointe type « Bon de commande signé ») "
                    "est requis avant notification."
                )
        if nouveau_statut == 'annule' and not self.motif_annulation:
            return False, "Motif d'annulation obligatoire."
        return True, "OK"

    def calculer_montants(self):
        total_ht = sum(l.montant_ht for l in self.lignes.all())
        self.montant_ht  = total_ht
        self.montant_tva = round(total_ht * self.taux_tva / 100, 2)
        self.montant_ttc = self.montant_ht + self.montant_tva


# ─────────────────────────────────────────────────────────────
# IMPUTATION BC (ligne budgétaire → BC)
# ─────────────────────────────────────────────────────────────

class ImputationBC(models.Model):
    bon_commande    = models.ForeignKey(BonCommande, on_delete=models.CASCADE, related_name='imputations')
    ligne_budgetaire = models.ForeignKey(
        LigneBudgetaire, on_delete=models.PROTECT, related_name='imputations',
    )
    montant         = models.DecimalField(max_digits=15, decimal_places=2)
    description     = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ['id']
        verbose_name = 'Imputation BC'
        verbose_name_plural = 'Imputations BC'

    def __str__(self):
        return f"BC {self.bon_commande.numero} → {self.ligne_budgetaire.code_nature} : {self.montant:,.0f}"


# ─────────────────────────────────────────────────────────────
# CONSOMMATION DIRECTE (sans BC)
# ─────────────────────────────────────────────────────────────

class ConsommationDirecte(models.Model):
    MOTIF_CHOICES = [
        ('achat_direct',      'Achat direct'),
        ('assistance_sociale', 'Assistance sociale'),
        ('urgence',           'Urgence'),
        ('remboursement',     'Remboursement'),
        ('correction',        'Correction'),
        ('autre',             'Autre'),
    ]

    ligne_budgetaire  = models.ForeignKey(
        LigneBudgetaire, on_delete=models.PROTECT, related_name='consommations_directes',
    )
    montant           = models.DecimalField(
        max_digits=12, decimal_places=2,
        validators=[MinValueValidator(Decimal('0.01'))],
    )
    motif             = models.CharField(max_length=20, choices=MOTIF_CHOICES)
    description       = models.TextField(blank=True, help_text="Détails supplémentaires")
    date_consommation = models.DateField()
    # ── Avis CAPRI (Règle R11) ──
    numero_capri      = models.CharField(
        max_length=50, blank=True, verbose_name="Numéro CAPRI",
        help_text="Numéro de l'avis CAPRI qui autorise cette consommation",
    )
    date_capri        = models.DateField(
        null=True, blank=True, verbose_name="Date d'émission CAPRI",
    )
    created_by        = models.ForeignKey(
        'Utilisateur', on_delete=models.SET_NULL, null=True,
    )
    created_at        = models.DateTimeField(auto_now_add=True)
    # Soft-delete : annulation admin (préserve la traçabilité du journal)
    est_annule        = models.BooleanField(default=False, db_index=True)
    annule_le         = models.DateTimeField(null=True, blank=True)
    annule_par        = models.ForeignKey(
        'Utilisateur', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='consommations_annulees',
    )
    motif_annulation  = models.TextField(blank=True)

    class Meta:
        ordering = ['-date_consommation', '-created_at']
        verbose_name = 'Consommation directe'
        verbose_name_plural = 'Consommations directes'
        # REFACTOR: couvre la sous-requête de with_aggregates (ligne + est_annule)
        # et les filtres de période des bilans (date_consommation)
        indexes = [
            models.Index(fields=['ligne_budgetaire', 'est_annule'], name='idx_conso_ligne_annule'),
            models.Index(fields=['date_consommation'], name='idx_conso_date'),
        ]

    @property
    def capri_manquant(self):
        """True si l'avis CAPRI (n° + date) n'est pas renseigné — à régulariser (R11)."""
        return not (self.numero_capri and self.date_capri)

    def __str__(self):
        flag = ' [ANNULÉE]' if self.est_annule else ''
        return f"{self.ligne_budgetaire.code_nature} — {self.montant:,.0f} FCFA ({self.get_motif_display()}){flag}"


# ─────────────────────────────────────────────────────────────
# PROLONGATION BC
# ─────────────────────────────────────────────────────────────

class ProlongationBC(models.Model):
    bon_commande            = models.ForeignKey(
        BonCommande, on_delete=models.CASCADE, related_name='prolongations',
    )
    ancienne_echeance       = models.DateField()
    nouvelle_echeance       = models.DateField()
    duree_prolongation_jours = models.PositiveIntegerField(default=0)
    motif                   = models.TextField()
    created_by              = models.ForeignKey('Utilisateur', on_delete=models.SET_NULL, null=True)
    created_at              = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Prolongation BC'
        verbose_name_plural = 'Prolongations BC'

    def save(self, *args, **kwargs):
        self.duree_prolongation_jours = (self.nouvelle_echeance - self.ancienne_echeance).days
        super().save(*args, **kwargs)
        BonCommande.objects.filter(pk=self.bon_commande_id).update(
            date_echeance=self.nouvelle_echeance,
        )

    def __str__(self):
        return (
            f"Prolongation {self.bon_commande.numero} : "
            f"{self.ancienne_echeance} → {self.nouvelle_echeance}"
        )


# ─────────────────────────────────────────────────────────────
# LIGNE BC (articles d'un BC)
# ─────────────────────────────────────────────────────────────

class LigneBC(models.Model):
    UNITE_CHOICES = [
        ('UN', 'Unité (UN)'), ('DA', 'DA'), ('KG', 'Kilogramme (KG)'),
        ('L', 'Litre (L)'), ('M', 'Mètre (M)'), ('M2', 'Mètre carré (M²)'),
        ('M3', 'Mètre cube (M³)'), ('FT', 'Forfait (FT)'), ('HR', 'Heure (HR)'),
        ('JR', 'Jour (JR)'), ('MOIS', 'Mois (MOIS)'), ('LOT', 'Lot (LOT)'),
    ]
    bon_commande      = models.ForeignKey(BonCommande, on_delete=models.CASCADE, related_name='lignes')
    reference_article = models.CharField(
        max_length=30, blank=True, verbose_name="Réf. Art",
        help_text="Code article saisi manuellement (ex: SER000072)",
    )
    designation       = models.CharField(max_length=200)
    unite             = models.CharField(max_length=10, choices=UNITE_CHOICES, default='UN')
    quantite          = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))],
    )
    prix_unitaire_ht  = models.DecimalField(max_digits=15, decimal_places=2)
    ordre             = models.IntegerField(default=1)

    class Meta:
        ordering = ['ordre']

    @property
    def montant_ht(self):
        return self.quantite * self.prix_unitaire_ht

    def __str__(self):
        return f"{self.designation} x{self.quantite}"


# ─────────────────────────────────────────────────────────────
# HISTORIQUE STATUT
# ─────────────────────────────────────────────────────────────

class HistoriqueStatut(models.Model):
    TYPE_CHOICES = [('DA', "Demande d'achat"), ('BC', 'Bon de commande')]
    type_entite  = models.CharField(max_length=2, choices=TYPE_CHOICES)
    entite_id    = models.IntegerField()
    ancien_statut  = models.CharField(max_length=20)
    nouveau_statut = models.CharField(max_length=20)
    utilisateur  = models.ForeignKey('Utilisateur', on_delete=models.SET_NULL, null=True)
    commentaire  = models.TextField(blank=True)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Historique de statut'
        verbose_name_plural = 'Historiques de statuts'


# ─────────────────────────────────────────────────────────────
# JOURNAL D'ACTIVITÉ (chaîne de hash SHA-256)
# ─────────────────────────────────────────────────────────────

class JournalActivite(models.Model):
    TYPE_CHOICES = [
        ('DA.create',          'Création DA'),
        ('DA.en_etude',        'Mise en étude DA'),
        ('DA.validate',        'Validation DA'),
        ('DA.refuse',          'Refus DA'),
        ('Offre.solliciter',   'Sollicitation prestataire'),
        ('Offre.saisir',       'Saisie offre reçue'),
        ('Offre.retenir',      'Rétention offre'),
        ('Offre.refuser',      'Refus offre'),
        ('BC.create',          'Création BC'),
        ('BC.notify',          'Notification BC'),
        ('BC.start',           'Mise en cours BC'),
        ('BC.execute',         'Exécution BC'),
        ('BC.cancel',          'Annulation BC'),
        ('BC.prolong',         'Prolongation BC'),
        ('PJ.upload',          'Upload pièce jointe'),
        ('PJ.delete',          'Suppression pièce jointe'),
        ('Consommation.create',  'Consommation directe'),
        ('Consommation.annuler', 'Annulation consommation directe'),
        ('Virement.annuler',     'Annulation virement'),
        ('Virement',           'Virement'),
        ('Tache.create',       'Création tâche'),
        ('Tache.edit',         'Modification tâche'),
        ('Tache.delete',       'Suppression tâche'),
        ('DA.edit',             'Modification DA'),
        ('BC.edit',             'Modification BC'),
        ('Prestataire.create', 'Création prestataire'),
        ('Prestataire.edit',   'Modification prestataire'),
        ('Prestataire.delete', 'Suppression prestataire'),
        ('Exercice.create',          'Création exercice'),
        ('Exercice.create_wizard',   'Création exercice (wizard)'),
        ('Exercice.activer',         'Activation exercice'),
        ('Exercice.cloture',         'Clôture exercice'),
        ('Exercice.reconduit',       'Reconduction exercice'),
        ('User.create',        'Création utilisateur'),
        ('User.edit',          'Modification utilisateur'),
        ('User.reset_pwd',     'Réinitialisation MDP'),
        ('User.delete',        'Suppression utilisateur'),
        ('User.toggle_actif',  'Activation/désactivation compte'),
        ('Parametres.seuil',   'Modification seuil alerte'),
        ('Import.excel',       'Import Excel'),
    ]
    type_action = models.CharField(max_length=30, choices=TYPE_CHOICES)
    description = models.TextField()
    entite_type = models.CharField(max_length=30, blank=True)
    entite_id   = models.IntegerField(null=True, blank=True)
    utilisateur = models.ForeignKey('Utilisateur', on_delete=models.SET_NULL, null=True)
    created_at  = models.DateTimeField(auto_now_add=True)
    prev_hash   = models.CharField(max_length=64, blank=True, default='')
    hash_chain  = models.CharField(max_length=64, blank=True, default='', db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Entrée du journal"
        verbose_name_plural = "Journal d'activité"
        # REFACTOR: chaque vue détail interroge l'historique par (entite_type, entite_id) ;
        # le journal filtre par type_action et created_at
        indexes = [
            models.Index(fields=['entite_type', 'entite_id'], name='idx_journal_entite'),
            models.Index(fields=['type_action'], name='idx_journal_action'),
        ]

    def __str__(self):
        return f"[{self.type_action}] {self.description}"

    def compute_hash(self) -> str:
        import hashlib
        payload = "|".join([
            self.prev_hash or 'GENESIS',
            self.type_action,
            self.description,
            self.entite_type or '',
            str(self.entite_id) if self.entite_id is not None else '',
            str(self.utilisateur_id) if self.utilisateur_id is not None else '',
            self.created_at.isoformat() if self.created_at else '',
        ])
        return hashlib.sha256(payload.encode('utf-8')).hexdigest()

    def save(self, *args, **kwargs):
        """
        Persiste l'entrée en chaînant prev_hash + hash_chain dans une seule transaction
        atomique avec verrou (COHE-13) — empêche 2 inserts concurrents de chaîner sur
        le même prev_hash, et garantit qu'aucune entrée n'existe sans hash_chain.
        """
        from django.db import transaction
        is_new = self.pk is None
        if is_new and not self.hash_chain:
            with transaction.atomic():
                # Lock toute la table pour sérialiser les inserts
                last = (
                    JournalActivite.objects
                    .select_for_update()
                    .order_by('-pk')
                    .first()
                )
                self.prev_hash = last.hash_chain if last else ''
                # Premier save pour obtenir pk + created_at (auto_now_add)
                super().save(*args, **kwargs)
                self.hash_chain = self.compute_hash()
                JournalActivite.objects.filter(pk=self.pk).update(
                    prev_hash=self.prev_hash,
                    hash_chain=self.hash_chain,
                )
        else:
            super().save(*args, **kwargs)


# ─────────────────────────────────────────────────────────────
# NOTIFICATION
# ─────────────────────────────────────────────────────────────

class Notification(models.Model):
    utilisateur = models.ForeignKey('Utilisateur', on_delete=models.CASCADE, related_name='notifications')
    type        = models.CharField(max_length=30)
    titre       = models.CharField(max_length=100)
    message     = models.TextField()
    entite_type = models.CharField(max_length=30, blank=True)
    entite_id   = models.IntegerField(null=True, blank=True)
    lu          = models.BooleanField(default=False)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.titre


# ─────────────────────────────────────────────────────────────
# ALERTE
# ─────────────────────────────────────────────────────────────

class Alerte(models.Model):
    tache        = models.ForeignKey(Tache, on_delete=models.CASCADE, related_name='alertes')
    type_alerte  = models.CharField(max_length=30)
    message      = models.TextField()
    seuil_atteint = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    lu           = models.BooleanField(default=False)
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.message


# ─────────────────────────────────────────────────────────────
# SÉQUENCE (compteur atomique)
# ─────────────────────────────────────────────────────────────

class Sequence(models.Model):
    key   = models.CharField(max_length=50, unique=True)
    value = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Séquence'
        verbose_name_plural = 'Séquences'

    def __str__(self):
        return f"{self.key} = {self.value}"


# ─────────────────────────────────────────────────────────────
# PIÈCE JOINTE
# ─────────────────────────────────────────────────────────────

class PieceJointe(models.Model):
    TYPE_CHOICES = [
        ('da',    "Demande d'achat"),
        ('bc',    'Bon de commande'),
        ('offre', 'Offre prestataire'),
        ('conso', 'Consommation directe'),
    ]
    TYPE_PIECE_CHOICES = [
        ('da_signee',          'DA signée par la Directrice'),
        ('avis_capri',         'Avis CAPRI scanné'),
        ('devis',              'Devis'),
        ('facture_proforma',   'Facture proforma'),
        ('bon_commande',       'Bon de commande signé'),
        ('facture',            'Facture'),
        ('pv_reception',       'PV de réception'),
        ('lettre_commande',    'Lettre de commande'),
        ('offre_technique',    'Offre technique'),
        ('autre',              'Autre'),
    ]
    MIME_AUTORISES = {
        'application/pdf',
        'image/jpeg', 'image/png', 'image/gif', 'image/webp',
        'application/msword',
        'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
        'application/vnd.ms-excel',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }
    TAILLE_MAX = 10 * 1024 * 1024  # 10 Mo

    type_entite  = models.CharField(max_length=10, choices=TYPE_CHOICES)
    entite_id    = models.IntegerField()
    type_piece   = models.CharField(
        max_length=25, choices=TYPE_PIECE_CHOICES, default='autre', blank=True,
        verbose_name='Type de document',
    )
    titre_personnalise = models.CharField(
        max_length=100, blank=True,
        verbose_name='Titre personnalisé',
        help_text="Pour le type « Autre » : préciser le titre du document.",
    )
    fichier      = models.FileField(upload_to='pieces_jointes/%Y/%m/')
    nom_original = models.CharField(max_length=255)
    taille       = models.PositiveIntegerField(default=0)
    uploaded_by  = models.ForeignKey(
        'Utilisateur', on_delete=models.SET_NULL, null=True,
        related_name='pieces_jointes',
    )
    created_at   = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Pièce jointe'
        verbose_name_plural = 'Pièces jointes'

    def __str__(self):
        return self.titre_affiche

    @property
    def titre_affiche(self):
        """Titre lisible. Le titre personnalisé complète n'importe quel type ;
        pour « Autre » il le remplace."""
        if self.type_piece == 'autre':
            return self.titre_personnalise or self.get_type_piece_display()
        base = self.get_type_piece_display() if self.type_piece else self.nom_original
        if self.titre_personnalise:
            return f"{base} — {self.titre_personnalise}"
        return base

    @property
    def extension(self):
        name = self.nom_original or ''
        return name.rsplit('.', 1)[-1].lower() if '.' in name else ''

    @property
    def icone(self):
        ext = self.extension
        if ext == 'pdf':                         return 'bi-file-earmark-pdf-fill'
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'): return 'bi-file-earmark-image-fill'
        if ext in ('doc', 'docx'):               return 'bi-file-earmark-word-fill'
        if ext in ('xls', 'xlsx'):               return 'bi-file-earmark-excel-fill'
        return 'bi-file-earmark-fill'

    @property
    def couleur_icone(self):
        ext = self.extension
        if ext == 'pdf':                         return '#E74C3C'
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'): return '#3498DB'
        if ext in ('doc', 'docx'):               return '#2980B9'
        if ext in ('xls', 'xlsx'):               return '#1A5632'
        return '#6c757d'

    def taille_lisible(self):
        s = self.taille
        if s < 1024:       return f"{s} o"
        if s < 1024 ** 2:  return f"{s / 1024:.1f} Ko"
        return f"{s / 1024 ** 2:.1f} Mo"


# ─────────────────────────────────────────────────────────────
# RÉPERTOIRE TÂCHES (catalogue réutilisable entre exercices)
# ─────────────────────────────────────────────────────────────

class RepertoireTache(models.Model):
    """Catalogue global des tâches — réutilisable à chaque exercice."""
    numero = models.CharField(max_length=20, unique=True)
    titre  = models.CharField(max_length=500)  # aligné sur Tache.titre
    actif  = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['numero']
        verbose_name = 'Répertoire tâche'
        verbose_name_plural = 'Répertoire tâches'

    def __str__(self):
        return f"{self.numero} — {self.titre}"


class RepertoireLigne(models.Model):
    """Catalogue global des lignes budgétaires — rattachées à une tâche du répertoire."""
    tache_repertoire = models.ForeignKey(
        RepertoireTache, on_delete=models.CASCADE, related_name='lignes_repertoire',
    )
    code_nature    = models.CharField(max_length=10)  # aligné sur LigneBudgetaire.code_nature
    libelle_nature = models.CharField(max_length=255)  # aligné sur LigneBudgetaire.libelle_nature
    actif          = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['code_nature']
        unique_together = ['tache_repertoire', 'code_nature']
        verbose_name = 'Répertoire ligne'
        verbose_name_plural = 'Répertoire lignes'

    def __str__(self):
        return f"{self.code_nature} — {self.libelle_nature}"


# ─────────────────────────────────────────────────────────────
# LOG ANNULATION (trace des annulations admin)
# ─────────────────────────────────────────────────────────────

class LogAnnulation(models.Model):
    TYPE_CHOICES = [
        ('consommation_directe', 'Consommation directe'),
        ('virement',             'Virement budgétaire'),
        ('demande_achat',        "Demande d'achat"),
        ('bon_commande',         'Bon de commande'),
    ]
    type_entite          = models.CharField(max_length=30, choices=TYPE_CHOICES)
    entite_id            = models.IntegerField()
    description_avant    = models.TextField()
    motif_annulation     = models.TextField()
    annule_par           = models.ForeignKey(
        'Utilisateur', on_delete=models.SET_NULL, null=True, related_name='annulations',
    )
    annule_le            = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-annule_le']
        verbose_name = 'Log annulation'
        verbose_name_plural = 'Logs annulations'

    def __str__(self):
        return f"Annulation {self.type_entite} #{self.entite_id} — {self.annule_le:%d/%m/%Y}"


# ─────────────────────────────────────────────────────────────
# JOURNAL DE PROGRAMMATION PAR BON DE COMMANDE (JP-BC)
# ─────────────────────────────────────────────────────────────

class PrestationProgrammee(models.Model):
    """Ligne du Journal de Programmation par Bon de Commande (JP-BC) de la DRH.

    Plan annuel des prestations à réaliser par BC, chargé en début d'exercice.
    Point de départ d'une Demande d'Achat : on sélectionne une prestation
    « programmée » qui pré-remplit la DA, puis la prestation passe « en cours ».
    """
    STATUT_CHOICES = [
        ('programmee', 'Programmée'),
        ('en_cours',   'En cours'),
        ('executee',   'Exécutée'),
        ('annulee',    'Annulée'),
    ]
    PERIODE_CHOICES = [
        ('quad',  'Quadrimestre (Mars – Juin)'),
        ('penta', 'Pentamestre (Juil. – Nov.)'),
    ]
    PRIORITE_CHOICES = [('1', 'Priorité 1'), ('2', 'Priorité 2')]
    NATURE_CHOICES = [
        ('APPRO',          'Approvisionnement (APPRO)'),
        ('TRAVAUX',        'Travaux'),
        ('PRESTATION_INT', 'Prestations intellectuelles'),
    ]

    exercice          = models.ForeignKey(
        'ExerciceBudgetaire', on_delete=models.CASCADE, related_name='prestations_programmees',
    )
    numero_ligne      = models.PositiveIntegerField(default=0, verbose_name="N° au journal")
    code_tache        = models.CharField(max_length=20, verbose_name="Code tâche")
    libelle_tache     = models.CharField(max_length=500, blank=True)
    code_nature       = models.CharField(max_length=10, blank=True)
    libelle_nature    = models.CharField(max_length=255, blank=True)
    objet_prestation  = models.TextField(verbose_name="Objet de la prestation")
    nature_prestation = models.CharField(max_length=20, choices=NATURE_CHOICES, default='APPRO')
    montant_ht        = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Montant HT")
    budget_previsionnel = models.DecimalField(
        max_digits=15, decimal_places=2, null=True, blank=True,
        verbose_name="Budget prévisionnel",
    )
    periode           = models.CharField(max_length=6, choices=PERIODE_CHOICES, default='quad')
    priorite          = models.CharField(max_length=2, choices=PRIORITE_CHOICES, default='1')
    statut            = models.CharField(max_length=12, choices=STATUT_CHOICES, default='programmee')
    # Lien optionnel vers la ligne budgétaire réelle (si l'exercice est chargé)
    ligne_budgetaire  = models.ForeignKey(
        'LigneBudgetaire', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prestations_programmees',
    )
    # DA générée à partir de cette prestation
    demande_achat     = models.OneToOneField(
        'DemandeAchat', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='prestation_source',
    )
    created_at        = models.DateTimeField(auto_now_add=True)
    updated_at        = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['periode', 'priorite', 'code_tache', 'numero_ligne']
        verbose_name = 'Prestation programmée'
        verbose_name_plural = 'Journal de programmation'
        # REFACTOR: filtres du journal (exercice + statut/periode/priorite)
        indexes = [
            models.Index(fields=['exercice', 'statut'], name='idx_presta_exo_statut'),
        ]

    def __str__(self):
        return f"[{self.get_periode_display()}] {self.code_tache} › {self.code_nature} — {self.objet_prestation[:40]}"

    @property
    def est_disponible(self):
        """Disponible pour générer une DA seulement si encore 'programmée'."""
        return self.statut == 'programmee'

    @property
    def montant_ttc_prevu(self):
        return (self.montant_ht * Decimal('1.1925')).quantize(Decimal('0.01'))

    @property
    def statut_couleur(self):
        return {
            'programmee': 'success', 'en_cours': 'warning',
            'executee': 'secondary', 'annulee': 'danger',
        }.get(self.statut, 'secondary')

    @property
    def nature_couleur(self):
        return {
            'APPRO': '#1B3A5C', 'TRAVAUX': '#E67E22', 'PRESTATION_INT': '#6C3483',
        }.get(self.nature_prestation, '#6c757d')
