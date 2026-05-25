# Générée manuellement — correctifs sécurité sprint 2
# 1. VirementBudgetaire : CASCADE → PROTECT sur tache_source et tache_dest
#    pour garantir l'immuabilité des virements (règle R5).
# 2. JournalActivite.type_action : max_length augmenté pour accueillir
#    les nouveaux types (Prestataire.create, Prestataire.delete, Tache.delete,
#    BC.start) et choices mis à jour.

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0006_journalactivite_hash_chain_journalactivite_prev_hash'),
    ]

    operations = [
        # --- R5 : protéger les virements contre la suppression en cascade ---
        migrations.AlterField(
            model_name='virementbudgetaire',
            name='tache_source',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='virements_sortants',
                to='core.tache',
            ),
        ),
        migrations.AlterField(
            model_name='virementbudgetaire',
            name='tache_dest',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='virements_entrants',
                to='core.tache',
            ),
        ),
        # --- R4 : nouveaux types d'action dans le journal ---
        migrations.AlterField(
            model_name='journalactivite',
            name='type_action',
            field=models.CharField(
                choices=[
                    ('DA.create', 'Création DA'),
                    ('DA.validate', 'Validation DA'),
                    ('DA.refuse', 'Refus DA'),
                    ('BC.create', 'Création BC'),
                    ('BC.notify', 'Notification BC'),
                    ('BC.start', 'Mise en cours BC'),
                    ('BC.execute', 'Exécution BC'),
                    ('BC.cancel', 'Annulation BC'),
                    ('Virement', 'Virement'),
                    ('Tache.create', 'Création tâche'),
                    ('Tache.edit', 'Modification tâche'),
                    ('Tache.delete', 'Suppression tâche'),
                    ('Prestataire.create', 'Création prestataire'),
                    ('Prestataire.delete', 'Suppression prestataire'),
                ],
                max_length=30,
            ),
        ),
    ]
