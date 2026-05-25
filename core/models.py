from django.db import models
from django.db.models import DecimalField, ExpressionWrapper, F, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from decimal import Decimal


class Utilisateur(AbstractUser):
    """Modèle utilisateur personnalisé avec rôles."""
    ROLE_CHOICES = [
        ('admin', 'Administrateur'),
        ('directeur_drh', 'Directeur DRH'),
        ('assistante_drh', 'Assistante DRH'),
        ('dag', 'DAG'),
        ('lecteur', 'Lecteur'),
    ]
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='lecteur')
    nom_complet = models.CharField(max_length=150, blank=True)
    must_change_password = models.BooleanField(
        default=False,
        help_text="Si vrai, l'utilisateur est force de changer son mot de passe a la prochaine connexion."
    )

    def __str__(self):
        return self.nom_complet or self.username

    def get_role_display_short(self):
        return dict(self.ROLE_CHOICES).get(self.role, self.role)


class ExerciceBudgetaire(models.Model):
    """Exercice budgétaire annuel."""
    annee = models.IntegerField(unique=True)
    date_debut = models.DateField()
    date_fin = models.DateField()
    montant_global = models.DecimalField(max_digits=15, decimal_places=2)
    STATUT_CHOICES = [('actif', 'Actif'), ('cloture', 'Clôturé')]
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='actif')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-annee']
        verbose_name = 'Exercice budgétaire'
        verbose_name_plural = 'Exercices budgétaires'

    def __str__(self):
        return f"Exercice {self.annee}"

    @classmethod
    def get_actif(cls):
        return cls.objects.filter(statut='actif').first()


class TacheQuerySet(models.QuerySet):
    """QuerySet annote pour Tache : budget_ajuste, consommation, solde calcules en SQL."""

    def with_aggregates(self):
        decimal_field = DecimalField(max_digits=15, decimal_places=2)
        return self.annotate(
            _consommation=Coalesce(
                Sum(
                    'bons_commande__montant_ttc',
                    filter=~Q(bons_commande__statut='annule'),
                ),
                Value(Decimal('0'), output_field=decimal_field),
            ),
        ).annotate(
            _budget_ajuste=ExpressionWrapper(
                F('montant_initial') + F('transactions_plus') - F('transactions_moins'),
                output_field=decimal_field,
            ),
        ).annotate(
            _solde=ExpressionWrapper(
                F('_budget_ajuste') - F('_consommation'),
                output_field=decimal_field,
            ),
        )


class TacheManager(models.Manager.from_queryset(TacheQuerySet)):
    """Manager Tache exposant with_aggregates() directement sur Tache.objects."""
    pass


class Tache(models.Model):
    """Tâche budgétaire."""
    exercice = models.ForeignKey(ExerciceBudgetaire, on_delete=models.CASCADE, related_name='taches')
    numero = models.CharField(max_length=10, unique=True)
    titre = models.CharField(max_length=200)
    code_nature = models.CharField(max_length=20, blank=True)
    libelle_nature = models.CharField(max_length=100, blank=True)
    montant_initial = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(0)])
    transactions_plus = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    transactions_moins = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    taux_previsionnel = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TacheManager()

    class Meta:
        ordering = ['numero']
        verbose_name = 'Tâche budgétaire'
        verbose_name_plural = 'Tâches budgétaires'

    def __str__(self):
        return f"{self.numero} — {self.titre}"

    @property
    def budget_ajuste(self):
        # Si l'instance a ete annotee via .with_aggregates(), on prend la valeur cachee.
        cached = getattr(self, '_budget_ajuste', None)
        if cached is not None:
            return cached
        return self.montant_initial + self.transactions_plus - self.transactions_moins

    @property
    def consommation(self):
        cached = getattr(self, '_consommation', None)
        if cached is not None:
            return cached
        total = self.bons_commande.exclude(statut='annule').aggregate(
            total=models.Sum('montant_ttc')
        )['total']
        return total or Decimal('0')

    @property
    def solde(self):
        cached = getattr(self, '_solde', None)
        if cached is not None:
            return cached
        return self.budget_ajuste - self.consommation

    @property
    def taux_consommation(self):
        budget = self.budget_ajuste
        if budget and budget > 0:
            return round((self.consommation / budget) * 100, 1)
        return Decimal('0')

    @property
    def taux_couleur(self):
        taux = float(self.taux_consommation)
        if taux >= 90:
            return 'danger'
        elif taux >= 70:
            return 'warning'
        return 'success'

    @property
    def transactions_display(self):
        """Affiche +/- pour le tableau."""
        plus = self.transactions_plus
        moins = self.transactions_moins
        if plus > 0 and moins > 0:
            return f"+{plus:,.0f} / -{moins:,.0f}"
        elif plus > 0:
            return f"+{plus:,.0f}"
        elif moins > 0:
            return f"-{moins:,.0f}"
        return "—"


class VirementBudgetaire(models.Model):
    """Transfert de fonds entre tâches."""
    tache_source = models.ForeignKey(Tache, on_delete=models.PROTECT, related_name='virements_sortants')
    tache_dest = models.ForeignKey(Tache, on_delete=models.PROTECT, related_name='virements_entrants')
    montant = models.DecimalField(max_digits=15, decimal_places=2, validators=[MinValueValidator(Decimal('0.01'))])
    motif = models.TextField()
    created_by = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Virement budgétaire'
        verbose_name_plural = 'Virements budgétaires'

    def __str__(self):
        return f"{self.tache_source.numero} → {self.tache_dest.numero} : {self.montant:,.0f} FCFA"


class Prestataire(models.Model):
    """Fournisseur ou prestataire de service."""
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


class DemandeAchat(models.Model):
    """Demande d'achat liée à une tâche."""
    STATUT_CHOICES = [
        ('cree', 'Créée'),
        ('en_etude', 'En étude'),
        ('validee', 'Validée'),
        ('refusee', 'Refusée'),
        ('bc_cree', 'BC créé'),
    ]
    reference = models.CharField(max_length=20, unique=True)
    exercice = models.ForeignKey(ExerciceBudgetaire, on_delete=models.CASCADE, related_name='demandes_achat')
    tache = models.ForeignKey(Tache, on_delete=models.CASCADE, related_name='demandes_achat')
    objet = models.CharField(max_length=200)
    montant_estime = models.DecimalField(max_digits=15, decimal_places=2)
    statut = models.CharField(max_length=15, choices=STATUT_CHOICES, default='cree')
    motif_refus = models.TextField(blank=True)
    created_by = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Demande d'achat"
        verbose_name_plural = "Demandes d'achat"

    def __str__(self):
        return f"{self.reference} — {self.objet}"

    @property
    def statut_couleur(self):
        colors = {'cree': 'secondary', 'en_etude': 'warning', 'validee': 'success', 'refusee': 'danger', 'bc_cree': 'info'}
        return colors.get(self.statut, 'secondary')

    # ---------------------------------------------------------------- state machine
    TRANSITIONS_AUTORISEES = {
        'cree':     ['en_etude'],
        'en_etude': ['validee', 'refusee'],
        'validee':  ['bc_cree'],
        'refusee':  [],
        'bc_cree':  [],
    }

    def peut_transiter_vers(self, nouveau_statut):
        """Vérifie si la transition est autorisée (retourne (bool, message_fr))."""
        autorisees = self.TRANSITIONS_AUTORISEES.get(self.statut, [])
        if nouveau_statut not in autorisees:
            return False, (
                f"Transition « {self.get_statut_display()} » → « {nouveau_statut} » interdite."
            )
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
        if nouveau_statut == 'refusee':
            if not self.motif_refus:
                return False, "Motif de refus obligatoire."
        return True, "OK"


class Offre(models.Model):
    """Offre d'un prestataire pour une DA (cycle complet : sollicitée → reçue → retenue/refusée)."""
    STATUT_CHOICES = [
        ('en_attente', 'En attente'),
        ('recue',      'Reçue'),
        ('retenue',    'Retenue'),
        ('refusee',    'Refusée'),
    ]
    demande           = models.ForeignKey(DemandeAchat, on_delete=models.CASCADE, related_name='offres')
    prestataire       = models.ForeignKey(Prestataire, on_delete=models.CASCADE)
    montant           = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    statut            = models.CharField(max_length=10, choices=STATUT_CHOICES, default='en_attente')
    motif_refus       = models.TextField(blank=True)
    date_sollicitation = models.DateTimeField(auto_now_add=True)
    date_reception    = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['date_sollicitation']
        verbose_name = 'Offre prestataire'

    def __str__(self):
        montant_str = f"{self.montant:,.0f} FCFA" if self.montant is not None else "—"
        return f"Offre {self.prestataire.nom} — {montant_str}"

    @property
    def est_en_retard(self):
        """Vrai si sollicité depuis plus de 7 jours sans réponse."""
        if self.statut != 'en_attente':
            return False
        from django.utils import timezone
        return (timezone.now() - self.date_sollicitation).days > 7

    @property
    def statut_couleur(self):
        return {
            'en_attente': 'warning',
            'recue':      'info',
            'retenue':    'success',
            'refusee':    'secondary',
        }.get(self.statut, 'secondary')

    @property
    def statut_icon(self):
        return {
            'en_attente': 'hourglass-split',
            'recue':      'envelope-check',
            'retenue':    'trophy',
            'refusee':    'x-circle',
        }.get(self.statut, 'circle')

    # ---------------------------------------------------------------- state machine
    TRANSITIONS_AUTORISEES = {
        'en_attente': ['recue'],
        'recue':      ['retenue', 'refusee'],
        'retenue':    [],
        'refusee':    [],
    }

    def peut_transiter_vers(self, nouveau_statut):
        """Vérifie si la transition est autorisée (retourne (bool, message_fr))."""
        autorisees = self.TRANSITIONS_AUTORISEES.get(self.statut, [])
        if nouveau_statut not in autorisees:
            return False, (
                f"Transition « {self.get_statut_display()} » → « {nouveau_statut} » interdite."
            )
        if nouveau_statut == 'retenue':
            deja_retenue = self.demande.offres.filter(statut='retenue').exclude(pk=self.pk).exists()
            if deja_retenue:
                return False, "Une offre est déjà retenue pour cette DA — une seule retenue autorisée."
        return True, "OK"


class BonCommande(models.Model):
    """Bon de commande officiel."""
    STATUT_CHOICES = [
        ('cree', 'Créé'),
        ('notifie', 'Notifié'),
        ('en_cours', 'En cours'),
        ('execute', 'Exécuté'),
        ('annule', 'Annulé'),
    ]
    TRANSITIONS = {
        'cree': ['notifie', 'annule'],
        'notifie': ['en_cours', 'annule'],
        'en_cours': ['execute', 'annule'],
        'execute': [],
        'annule': [],
    }
    numero = models.CharField(max_length=20, unique=True)
    demande = models.ForeignKey(DemandeAchat, on_delete=models.CASCADE, related_name='bons_commande', null=True, blank=True)
    tache = models.ForeignKey(Tache, on_delete=models.CASCADE, related_name='bons_commande')
    exercice = models.ForeignKey(ExerciceBudgetaire, on_delete=models.CASCADE, related_name='bons_commande')
    prestataire = models.ForeignKey(Prestataire, on_delete=models.CASCADE, related_name='bons_commande')
    direction = models.CharField(max_length=100, default='Direction des Ressources Humaines')
    date_emission = models.DateField(auto_now_add=True)
    date_notification = models.DateField(null=True, blank=True)
    taux_tva = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('19.25'))
    montant_ht = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_tva = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    montant_ttc = models.DecimalField(max_digits=15, decimal_places=2, default=0)
    statut = models.CharField(max_length=10, choices=STATUT_CHOICES, default='cree', db_index=True)
    motif_annulation = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

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

    @property
    def statut_couleur(self):
        colors = {'cree': 'secondary', 'notifie': 'info', 'en_cours': 'primary', 'execute': 'success', 'annule': 'danger'}
        return colors.get(self.statut, 'secondary')

    def peut_transiter(self, nouveau_statut):
        return nouveau_statut in self.TRANSITIONS.get(self.statut, [])

    def peut_transiter_vers(self, nouveau_statut):
        """Vérifie la transition + conditions métier (retourne (bool, message_fr))."""
        if nouveau_statut not in self.TRANSITIONS.get(self.statut, []):
            return False, (
                f"Transition « {self.get_statut_display()} » → « {nouveau_statut} » interdite."
            )
        if nouveau_statut == 'notifie':
            has_pj = PieceJointe.objects.filter(
                type_entite='bc', entite_id=self.pk, type_piece='bon_commande'
            ).exists()
            if not has_pj:
                return False, (
                    "Un bon de commande signé (pièce jointe de type "
                    "« Bon de commande signé ») est requis avant notification."
                )
        return True, "OK"

    def calculer_montants(self):
        total_ht = sum(l.montant_ht for l in self.lignes.all())
        self.montant_ht = total_ht
        self.montant_tva = round(total_ht * self.taux_tva / 100, 2)
        self.montant_ttc = self.montant_ht + self.montant_tva


class LigneBC(models.Model):
    """Ligne d'article d'un bon de commande."""
    bon_commande = models.ForeignKey(BonCommande, on_delete=models.CASCADE, related_name='lignes')
    designation = models.CharField(max_length=200)
    quantite = models.IntegerField(validators=[MinValueValidator(1)])
    prix_unitaire_ht = models.DecimalField(max_digits=15, decimal_places=2)
    ordre = models.IntegerField(default=1)

    class Meta:
        ordering = ['ordre']

    @property
    def montant_ht(self):
        return self.quantite * self.prix_unitaire_ht

    def __str__(self):
        return f"{self.designation} x{self.quantite}"


class HistoriqueStatut(models.Model):
    """Historique des changements de statut (DA et BC)."""
    TYPE_CHOICES = [('DA', 'Demande d\'achat'), ('BC', 'Bon de commande')]
    type_entite = models.CharField(max_length=2, choices=TYPE_CHOICES)
    entite_id = models.IntegerField()
    ancien_statut = models.CharField(max_length=20)
    nouveau_statut = models.CharField(max_length=20)
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    commentaire = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Historique de statut'
        verbose_name_plural = 'Historiques de statuts'


class JournalActivite(models.Model):
    """
    Journal d'activite immuable, scelle par une chaine de hash SHA-256.
    Chaque entree contient :
      - hash_chain : SHA-256(prev_hash + payload de l'entree)
      - prev_hash  : hash de l'entree precedente (ou GENESIS pour la 1re)
    Toute modification a posteriori est detectable via la commande
    `manage.py verify_audit_chain`.
    """
    TYPE_CHOICES = [
        ('DA.create',           'Création DA'),
        ('DA.en_etude',         'Mise en étude DA'),
        ('DA.validate',         'Validation DA'),
        ('DA.refuse',           'Refus DA'),
        ('Offre.solliciter',    'Sollicitation prestataire'),
        ('Offre.saisir',        'Saisie offre reçue'),
        ('Offre.retenir',       'Rétention offre'),
        ('Offre.refuser',       'Refus offre'),
        ('BC.create',           'Création BC'),
        ('BC.notify',           'Notification BC'),
        ('BC.start',            'Mise en cours BC'),
        ('BC.execute',          'Exécution BC'),
        ('BC.cancel',           'Annulation BC'),
        ('PJ.upload',           'Upload pièce jointe'),
        ('PJ.delete',           'Suppression pièce jointe'),
        ('Virement',            'Virement'),
        ('Tache.create',        'Création tâche'),
        ('Tache.edit',          'Modification tâche'),
        ('Tache.delete',        'Suppression tâche'),
        ('Prestataire.create',  'Création prestataire'),
        ('Prestataire.delete',  'Suppression prestataire'),
        ('Exercice.create',     'Création exercice'),
        ('User.create',         'Création utilisateur'),
        ('User.edit',           'Modification utilisateur'),
        ('User.reset_pwd',      'Réinitialisation MDP'),
        ('User.delete',         'Suppression utilisateur'),
    ]
    type_action = models.CharField(max_length=30, choices=TYPE_CHOICES)
    description = models.TextField()
    entite_type = models.CharField(max_length=30, blank=True)
    entite_id = models.IntegerField(null=True, blank=True)
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # Chaine de hash (rempli automatiquement a la creation)
    prev_hash = models.CharField(max_length=64, blank=True, default='')
    hash_chain = models.CharField(max_length=64, blank=True, default='', db_index=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = "Entrée du journal"
        verbose_name_plural = "Journal d'activité"

    def __str__(self):
        return f"[{self.type_action}] {self.description}"

    def compute_hash(self) -> str:
        """Calcule le hash SHA-256 de l'entree (prev_hash + payload canonique)."""
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
        from django.db import transaction
        is_new = self.pk is None
        super().save(*args, **kwargs)  # cree pk + created_at (auto_now_add)
        if is_new and not self.hash_chain:
            # select_for_update() sérialise les créations concurrentes et évite
            # les forks dans la chaîne (deux entrées avec le même prev_hash).
            with transaction.atomic():
                last = (
                    JournalActivite.objects
                    .exclude(pk=self.pk)
                    .select_for_update()
                    .order_by('-pk')
                    .first()
                )
                self.prev_hash = last.hash_chain if last else ''
                self.hash_chain = self.compute_hash()
                JournalActivite.objects.filter(pk=self.pk).update(
                    prev_hash=self.prev_hash,
                    hash_chain=self.hash_chain,
                )


class Notification(models.Model):
    """Notification pour un utilisateur."""
    utilisateur = models.ForeignKey(Utilisateur, on_delete=models.CASCADE, related_name='notifications')
    type = models.CharField(max_length=30)
    titre = models.CharField(max_length=100)
    message = models.TextField()
    entite_type = models.CharField(max_length=30, blank=True)
    entite_id = models.IntegerField(null=True, blank=True)
    lu = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.titre


class Alerte(models.Model):
    """Alerte de dépassement budgétaire."""
    tache = models.ForeignKey(Tache, on_delete=models.CASCADE, related_name='alertes')
    type_alerte = models.CharField(max_length=30)
    message = models.TextField()
    seuil_atteint = models.DecimalField(max_digits=5, decimal_places=2, null=True)
    lu = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.message


class Sequence(models.Model):
    """
    Compteur monotone partage pour la numerotation officielle (BC, DA, etc.).
    Toute incrementation doit passer par SequenceService.next_value() afin
    d'utiliser select_for_update et eviter les collisions concurrentes.
    """
    key = models.CharField(max_length=50, unique=True)
    value = models.IntegerField(default=0)

    class Meta:
        verbose_name = 'Sequence'
        verbose_name_plural = 'Sequences'

    def __str__(self):
        return f"{self.key} = {self.value}"


class PieceJointe(models.Model):
    """
    Pièce jointe associée à une DA, un BC ou une Offre.
    Utilise un champ générique (type_entite + entite_id) pour éviter
    une multiplication de ForeignKeys.
    """
    TYPE_CHOICES = [
        ('da',    "Demande d'achat"),
        ('bc',    'Bon de commande'),
        ('offre', 'Offre prestataire'),
    ]
    TYPE_PIECE_CHOICES = [
        ('devis',            'Devis'),
        ('facture_proforma', 'Facture proforma'),
        ('bon_commande',     'Bon de commande signé'),
        ('facture',          'Facture'),
        ('pv_reception',     'PV de réception'),
        ('autre',            'Autre'),
    ]
    # Types MIME autorisés (vérifiés côté view)
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
        max_length=20, choices=TYPE_PIECE_CHOICES, default='autre', blank=True,
        verbose_name='Type de document',
    )
    fichier      = models.FileField(upload_to='pieces_jointes/%Y/%m/')
    nom_original = models.CharField(max_length=255)
    taille       = models.PositiveIntegerField(default=0)
    uploaded_by  = models.ForeignKey(
        Utilisateur, on_delete=models.SET_NULL, null=True,
        related_name='pieces_jointes'
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
        if ext == 'pdf':
            return 'bi-file-earmark-pdf-fill'
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            return 'bi-file-earmark-image-fill'
        if ext in ('doc', 'docx'):
            return 'bi-file-earmark-word-fill'
        if ext in ('xls', 'xlsx'):
            return 'bi-file-earmark-excel-fill'
        return 'bi-file-earmark-fill'

    @property
    def couleur_icone(self):
        ext = self.extension
        if ext == 'pdf':
            return '#E74C3C'
        if ext in ('jpg', 'jpeg', 'png', 'gif', 'webp'):
            return '#3498DB'
        if ext in ('doc', 'docx'):
            return '#2980B9'
        if ext in ('xls', 'xlsx'):
            return '#1A5632'
        return '#6c757d'

    def taille_lisible(self):
        s = self.taille
        if s < 1024:
            return f"{s} o"
        if s < 1024 ** 2:
            return f"{s / 1024:.1f} Ko"
        return f"{s / 1024 ** 2:.1f} Mo"
