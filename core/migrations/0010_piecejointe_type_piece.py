# Migration : ajout du champ type_piece sur PieceJointe
# pour distinguer devis / bon_commande signé / facture / etc.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0009_piece_jointe'),
    ]

    operations = [
        migrations.AddField(
            model_name='piecejointe',
            name='type_piece',
            field=models.CharField(
                blank=True,
                choices=[
                    ('devis',            'Devis'),
                    ('facture_proforma', 'Facture proforma'),
                    ('bon_commande',     'Bon de commande signé'),
                    ('facture',          'Facture'),
                    ('pv_reception',     'PV de réception'),
                    ('autre',            'Autre'),
                ],
                default='autre',
                max_length=20,
                verbose_name='Type de document',
            ),
        ),
    ]
