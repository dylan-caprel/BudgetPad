# Journal de Programmation par Bon de Commande (JP-BC) — modèle PrestationProgrammee

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0011_piecejointe_titre'),
    ]

    operations = [
        migrations.CreateModel(
            name='PrestationProgrammee',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('numero_ligne', models.PositiveIntegerField(default=0, verbose_name='N° au journal')),
                ('code_tache', models.CharField(max_length=20, verbose_name='Code tâche')),
                ('libelle_tache', models.CharField(blank=True, max_length=500)),
                ('code_nature', models.CharField(blank=True, max_length=10)),
                ('libelle_nature', models.CharField(blank=True, max_length=255)),
                ('objet_prestation', models.TextField(verbose_name="Objet de la prestation")),
                ('nature_prestation', models.CharField(choices=[('APPRO', 'Approvisionnement (APPRO)'), ('TRAVAUX', 'Travaux'), ('PRESTATION_INT', 'Prestations intellectuelles')], default='APPRO', max_length=20)),
                ('montant_ht', models.DecimalField(decimal_places=2, default=0, max_digits=15, verbose_name='Montant HT')),
                ('budget_previsionnel', models.DecimalField(blank=True, decimal_places=2, max_digits=15, null=True, verbose_name='Budget prévisionnel')),
                ('periode', models.CharField(choices=[('quad', 'Quadrimestre (Mars – Juin)'), ('penta', 'Pentamestre (Juil. – Nov.)')], default='quad', max_length=6)),
                ('priorite', models.CharField(choices=[('1', 'Priorité 1'), ('2', 'Priorité 2')], default='1', max_length=2)),
                ('statut', models.CharField(choices=[('programmee', 'Programmée'), ('en_cours', 'En cours'), ('executee', 'Exécutée'), ('annulee', 'Annulée')], default='programmee', max_length=12)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('demande_achat', models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prestation_source', to='core.demandeachat')),
                ('exercice', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='prestations_programmees', to='core.exercicebudgetaire')),
                ('ligne_budgetaire', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='prestations_programmees', to='core.lignebudgetaire')),
            ],
            options={
                'verbose_name': 'Prestation programmée',
                'verbose_name_plural': 'Journal de programmation',
                'ordering': ['periode', 'priorite', 'code_tache', 'numero_ligne'],
            },
        ),
    ]
