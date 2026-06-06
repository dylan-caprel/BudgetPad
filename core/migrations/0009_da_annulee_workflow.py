# Workflow DA : « Refusée » fusionnée dans « Annulée », « En étude » → « Transmise DAG »
#  - Migre les DA existantes au statut 'refusee' vers 'annulee'
#  - Aligne l'historique de statut (audit) sur la nouvelle terminologie

from django.db import migrations, models


def refusee_vers_annulee(apps, schema_editor):
    DemandeAchat = apps.get_model('core', 'DemandeAchat')
    DemandeAchat.objects.filter(statut='refusee').update(statut='annulee')

    HistoriqueStatut = apps.get_model('core', 'HistoriqueStatut')
    HistoriqueStatut.objects.filter(type_entite='DA', ancien_statut='refusee').update(ancien_statut='annulee')
    HistoriqueStatut.objects.filter(type_entite='DA', nouveau_statut='refusee').update(nouveau_statut='annulee')


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_alter_journalactivite_type_action'),
    ]

    operations = [
        migrations.RunPython(refusee_vers_annulee, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='demandeachat',
            name='statut',
            field=models.CharField(
                choices=[
                    ('cree', 'Créée'),
                    ('en_etude', 'Transmise DAG'),
                    ('validee', 'Validée'),
                    ('bc_cree', 'BC créé'),
                    ('annulee', 'Annulée'),
                ],
                default='cree', max_length=15,
            ),
        ),
        migrations.AlterField(
            model_name='demandeachat',
            name='motif_refus',
            field=models.TextField(blank=True, verbose_name="Motif d'annulation"),
        ),
    ]
