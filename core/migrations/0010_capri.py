# Règle R11 — Avis CAPRI sur les imputations (BonCommande + ConsommationDirecte)
#  Champs nullables : les enregistrements existants restent valides en base,
#  mais sont signalés « CAPRI à régulariser » côté application (obligatoire à la saisie).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_da_annulee_workflow'),
    ]

    operations = [
        migrations.AddField(
            model_name='boncommande',
            name='numero_capri',
            field=models.CharField(
                blank=True, default='', max_length=50,
                help_text="Numéro de l'avis CAPRI qui autorise cette imputation",
                verbose_name='Numéro CAPRI',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='boncommande',
            name='date_capri',
            field=models.DateField(blank=True, null=True, verbose_name="Date d'émission CAPRI"),
        ),
        migrations.AddField(
            model_name='consommationdirecte',
            name='numero_capri',
            field=models.CharField(
                blank=True, default='', max_length=50,
                help_text="Numéro de l'avis CAPRI qui autorise cette consommation",
                verbose_name='Numéro CAPRI',
            ),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='consommationdirecte',
            name='date_capri',
            field=models.DateField(blank=True, null=True, verbose_name="Date d'émission CAPRI"),
        ),
    ]
