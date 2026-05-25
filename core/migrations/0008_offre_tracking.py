# Migration : enrichissement du modèle Offre pour le suivi complet du cycle
# de consultation des prestataires (sollicitation → réception → décision).
#
# Changements :
#   - montant : null/blank autorisés (l'offre peut être saisie avant réception)
#   - statut  : ajout des statuts 'en_attente' et 'recue' + default changé
#   - date_sollicitation : DateTimeField auto (défaut = maintenant pour lignes existantes)
#   - date_reception     : DateTimeField nullable (rempli lors de la saisie du montant)

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0007_protect_virements_and_journal_types'),
    ]

    operations = [
        # 1. Rendre montant nullable (offre sollicitée sans montant connu)
        migrations.AlterField(
            model_name='offre',
            name='montant',
            field=models.DecimalField(
                decimal_places=2, max_digits=15,
                null=True, blank=True,
            ),
        ),

        # 2. Mettre à jour les choix et le défaut du statut
        migrations.AlterField(
            model_name='offre',
            name='statut',
            field=models.CharField(
                choices=[
                    ('en_attente', 'En attente'),
                    ('recue',      'Reçue'),
                    ('retenue',    'Retenue'),
                    ('refusee',    'Refusée'),
                ],
                default='en_attente',
                max_length=10,
            ),
        ),

        # 3. Ajouter date_sollicitation (défaut = now pour les lignes existantes)
        migrations.AddField(
            model_name='offre',
            name='date_sollicitation',
            field=models.DateTimeField(
                auto_now_add=True,
                default=django.utils.timezone.now,
            ),
            preserve_default=False,
        ),

        # 4. Ajouter date_reception nullable
        migrations.AddField(
            model_name='offre',
            name='date_reception',
            field=models.DateTimeField(null=True, blank=True),
        ),
    ]
