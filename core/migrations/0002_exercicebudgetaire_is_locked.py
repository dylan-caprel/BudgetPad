from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='exercicebudgetaire',
            name='is_locked',
            field=models.BooleanField(
                default=False,
                help_text="Si vrai, l'exercice est en lecture seule — aucune création/modification autorisée.",
            ),
        ),
    ]
