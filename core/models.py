from django.db import models
from django.db.models import (
    Case, DecimalField, ExpressionWrapper, F, Q, Sum, Value, When,
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

class TacheQuerySet(models.QuerySet):
    def with_aggregates(self):
        df = DecimalField(max_digits=15, decimal_places=2)
        zero = Value(Decimal('0'), output_field=df)
        return (
            self
            .annotate(
                total_budget_initial=Coalesce(
                    Sum('lignes__montant_initial', filter=Q(lignes__actif=True)),
                    zero,
                ),
                total_transfert_plus=Coalesce(
                    Sum('lignes__virements_entrants__montant', filter=Q(lignes__actif=True)),
                    zero,
                ),
                total_transfert_moins=Coalesce(
                    Sum('lignes__virements_sortants__montant', filter=Q(lignes__actif=True)),
                    zero,
                ),
            )
            .annotate(
                total_budget_ajuste=ExpressionWrapper(
                    F('total_budget_initial') + F('total_transfert_plus') - F('total_transfert_moins'),
                    output_field=df,
                ),
            )
            .annotate(
                total_conso_bc=Coalesce(
                    Sum(
                        'lignes__imputations__montant',
                        filter=(
                            Q(lignes__actif=True)
                            & ~Q(lignes__imputations__bon_commande__statut='annule')
                        ),
                    ),
                    zero,
                ),
            )
            .annotate(
                total_conso_directe=Coalesce(
                    Sum(
                        'lignes__consommations_directes__montant',
                        filter=(
                            Q(lignes__actif=True)
                            & Q(lignes__consommations_directes__est_annule=False)
                        ),
                    ),
                    zero,
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
                transfert_plus=Coalesce(Sum('virements_entrants__montant'), zero),
                transfert_moins=Coalesce(Sum('virements_sortants__montant'), zero),
            )
            .annotate(
                budget_ajuste=ExpressionWrapper(
                    F('montant_initial') + F('transfert_plus') - F('transfert_moins'),
                    output_field=df,
                ),
            )
            .annotate(
                consommation_bc=Coalesce(
                    Sum(
                        'imputations__montant',
                        filter=~Q(imputations__bon_commande__statut='annule'),
                    ),
                    zero,
                ),
            )
            .annotate(
                consommation_directe=Coalesce(
                    Sum(
                        'consommations_directes__montant',
                        filter=Q(consommations_directes__est_annule=False),
                    ),
                    zero,
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
        ('en_etude', 'En étude'),
        ('validee',  'Validée'),
        ('refusee',  'Refusée'),
        ('bc_cree',  'BC créé'),
    ]
    reference = models.CharField(max_length=20, unique=True)
    exercice = models.ForeignKey(
        ExerciceBudgetaire, on_delete=models.CASCADE, related_name='demandes_achat',
    )
    tache = models.ForeignKey(Tache, on_delete=models.CASCADE, related_name='demandes_achat')
    objet = models.CharField(max_length=200)
    montant_estime = models.DecimalField(max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=15, choices=STATUT_CHOICES, default='cree')
    motif_refus = models.TextField(blank=True)
    created_by = models.ForeignKey('Utilisateur', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Demande d'achat"
        verbose_name_plural = "Demandes d'achat"

    def __str__(self):
        return f"{self.reference} — {self.objet}"

    @property
    def statut_couleur(self):
        return {
            'cree': 'secondary', 'en_etude': 'warning', 'validee': 'success',
            'refusee': 'danger', 'bc_cree': 'info',
        }.get(self.statut, 'secondary')

    TRANSITIONS_AUTORISEES = {
        'cree':     ['en_etude'],
        'en_etude': ['validee', 'refusee'],
        'validee':  ['bc_cree'],
        'refusee':  [],
        'bc_cree':  [],
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
            pj_count = PieceJointe.objects.filter(type_entite='da', entite_id=self.pk).count()
            if pj_count == 0:
                return False, "Au moins 1 pièce jointe est requise pour valider une DA."
        if nouveau_statut == 'refusee' and not self.motif_refus:
            return False, "Motif de refus obligatoire."
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
    numero           = models.CharField(max_length=20, unique=True)
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
    date_emission    = models.DateField(auto_now_add=True)
    date_notification = models.DateField(null=True, blank=True)
    delai_execution_jours = models.PositiveIntegerField(
        null=True, blank=True,
        help_text="Délai accordé au prestataire pour l'exécution (en jours)",
    )
    date_echeance    = models.DateField(null=True, blank=True)
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
        ]

    def __str__(self):
        return f"{self.numero} — {self.prestataire.nom}"

    def save(self, *args, **kwargs):
        if self.date_notification and self.delai_execution_jours:
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
    bon_commande     = models.ForeignKey(BonCommande, on_delete=models.CASCADE, related_name='lignes')
    designation      = models.CharField(max_length=200)
    quantite         = models.IntegerField(validators=[MinValueValidator(1)])
    prix_unitaire_ht = models.DecimalField(max_digits=15, decimal_places=2)
    ordre            = models.IntegerField(default=1)

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
        ('Prestataire.create', 'Création prestataire'),
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
    ]
    TYPE_PIECE_CHOICES = [
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
        return self.nom_original

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
