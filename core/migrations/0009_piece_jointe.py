# Migration : ajout du modèle PieceJointe pour la gestion des pièces jointes
# sur les DA, BC et Offres prestataires.

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_offre_tracking'),
    ]

    operations = [
        migrations.CreateModel(
            name='PieceJointe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('type_entite', models.CharField(
                    choices=[('da', "Demande d'achat"), ('bc', 'Bon de commande'), ('offre', 'Offre prestataire')],
                    max_length=10,
                )),
                ('entite_id', models.IntegerField()),
                ('fichier', models.FileField(upload_to='pieces_jointes/%Y/%m/')),
                ('nom_original', models.CharField(max_length=255)),
                ('taille', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('uploaded_by', models.ForeignKey(
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='pieces_jointes',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'verbose_name': 'Pièce jointe',
                'verbose_name_plural': 'Pièces jointes',
                'ordering': ['-created_at'],
            },
        ),
    ]
