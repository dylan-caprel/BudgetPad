# Pièces jointes : titre personnalisé + nouveaux types (DA signée, Avis CAPRI),
# et type_entite « conso » (consommation directe).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0010_capri'),
    ]

    operations = [
        migrations.AddField(
            model_name='piecejointe',
            name='titre_personnalise',
            field=models.CharField(
                blank=True, default='', max_length=100,
                help_text="Pour le type « Autre » : préciser le titre du document.",
                verbose_name='Titre personnalisé',
            ),
            preserve_default=False,
        ),
        migrations.AlterField(
            model_name='piecejointe',
            name='type_piece',
            field=models.CharField(
                blank=True, default='autre', max_length=25,
                verbose_name='Type de document',
                choices=[
                    ('da_signee', 'DA signée par la Directrice'),
                    ('avis_capri', 'Avis CAPRI scanné'),
                    ('devis', 'Devis'),
                    ('facture_proforma', 'Facture proforma'),
                    ('bon_commande', 'Bon de commande signé'),
                    ('facture', 'Facture'),
                    ('pv_reception', 'PV de réception'),
                    ('lettre_commande', 'Lettre de commande'),
                    ('offre_technique', 'Offre technique'),
                    ('autre', 'Autre'),
                ],
            ),
        ),
        migrations.AlterField(
            model_name='piecejointe',
            name='type_entite',
            field=models.CharField(
                max_length=10,
                choices=[
                    ('da', "Demande d'achat"),
                    ('bc', 'Bon de commande'),
                    ('offre', 'Offre prestataire'),
                    ('conso', 'Consommation directe'),
                ],
            ),
        ),
    ]
