# Migration — Mise en conformité format réel PAD
#  - DA : nature_prestation / periode_engagement / priorite + ref format DAC
#  - BC : delai_execution_semaines / condition_paiement / rib_paiement / objet + num format STD
#  - LigneBC : reference_article (saisie manuelle) / unite / quantite décimale

from decimal import Decimal
import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_da_par_ligne'),
    ]

    operations = [
        # ── DemandeAchat ──────────────────────────────────────────────
        migrations.AddField(
            model_name='demandeachat',
            name='nature_prestation',
            field=models.CharField(
                blank=True, default='', max_length=20,
                choices=[
                    ('APPRO', 'Approvisionnement (APPRO)'),
                    ('Trx', 'Travaux (Trx)'),
                    ('Prestat.Int', 'Prestation intellectuelle (Prestat.Int)'),
                    ('Autre', 'Autre'),
                ],
                verbose_name='Nature de la prestation',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='demandeachat',
            name='periode_engagement',
            field=models.CharField(
                blank=True, default='', max_length=5,
                choices=[
                    ('P1', 'Période 1 (Mars — Juin)'),
                    ('P2', 'Période 2 (Juillet — Novembre)'),
                ],
                verbose_name="Période d'engagement",
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='demandeachat',
            name='priorite',
            field=models.CharField(
                blank=True, default='', max_length=2,
                choices=[('1', 'Priorité 1'), ('2', 'Priorité 2')],
                verbose_name='Priorité',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='demandeachat',
            name='reference',
            field=models.CharField(
                blank=True, max_length=30, unique=True,
                help_text='Laisser vide pour auto-génération au format DAC{AAMM}DLA{NNNNN}',
            ),
        ),

        # ── BonCommande ───────────────────────────────────────────────
        migrations.AddField(
            model_name='boncommande',
            name='delai_execution_semaines',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text="Ex: 4 pour 4 semaines. La date d'échéance est calculée automatiquement.",
                verbose_name="Délai d'exécution (semaines)",
            ),
        ),
        migrations.AddField(
            model_name='boncommande',
            name='condition_paiement',
            field=models.CharField(
                default='virement_60', max_length=100,
                choices=[
                    ('virement_60', 'Virement 60 jours fin de mois'),
                    ('virement_30', 'Virement 30 jours fin de mois'),
                    ('comptant', 'Paiement comptant'),
                    ('autre', 'Autre'),
                ],
                verbose_name='Condition de paiement',
            ),
        ),
        migrations.AddField(
            model_name='boncommande',
            name='rib_paiement',
            field=models.CharField(
                blank=True, default='', max_length=50,
                help_text='Ex: 10003 03900 06000053467 94',
                verbose_name='RIB de paiement',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='boncommande',
            name='objet',
            field=models.TextField(blank=True, default='', verbose_name='Objet du bon de commande'),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='boncommande',
            name='numero',
            field=models.CharField(
                blank=True, max_length=30, unique=True,
                help_text='Laisser vide pour auto-génération au format STD{AAMM}DLA{NNNNN}',
            ),
        ),
        migrations.AlterField(
            model_name='boncommande',
            name='delai_execution_jours',
            field=models.PositiveIntegerField(
                blank=True, null=True,
                help_text="Délai accordé au prestataire pour l'exécution (en jours) — legacy",
            ),
        ),

        # ── LigneBC ───────────────────────────────────────────────────
        migrations.AddField(
            model_name='lignebc',
            name='reference_article',
            field=models.CharField(
                blank=True, default='', max_length=30,
                help_text='Code article saisi manuellement (ex: SER000072)',
                verbose_name='Réf. Art',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='lignebc',
            name='unite',
            field=models.CharField(
                default='UN', max_length=10,
                choices=[
                    ('UN', 'Unité (UN)'), ('DA', 'DA'), ('KG', 'Kilogramme (KG)'),
                    ('L', 'Litre (L)'), ('M', 'Mètre (M)'), ('M2', 'Mètre carré (M²)'),
                    ('M3', 'Mètre cube (M³)'), ('FT', 'Forfait (FT)'), ('HR', 'Heure (HR)'),
                    ('JR', 'Jour (JR)'), ('MOIS', 'Mois (MOIS)'), ('LOT', 'Lot (LOT)'),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='lignebc',
            name='quantite',
            field=models.DecimalField(
                decimal_places=2, max_digits=10,
                validators=[django.core.validators.MinValueValidator(Decimal('0.01'))],
            ),
        ),
    ]
