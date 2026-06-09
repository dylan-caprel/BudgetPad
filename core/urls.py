from django.urls import path
from . import views

urlpatterns = [
    # Auth
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('password/change/', views.password_change_forced_view, name='password_change_forced'),

    # Dashboard
    path('', views.dashboard_view, name='dashboard'),

    # Tâches
    path('taches/', views.taches_list, name='taches_list'),
    path('taches/creer/', views.tache_create, name='tache_create'),
    path('taches/<int:pk>/detail/', views.tache_detail, name='tache_detail'),
    path('taches/<int:pk>/modifier/', views.tache_edit, name='tache_edit'),
    path('taches/<int:pk>/supprimer/', views.tache_delete, name='tache_delete'),

    # API interne
    path('api/ligne/<int:pk>/solde/', views.api_ligne_solde, name='api_ligne_solde'),

    # Transferts
    path('virements/', views.virements_list, name='virements_list'),
    path('virements/creer/', views.virement_create, name='virement_create'),
    path('virements/<int:pk>/detail/', views.virement_detail, name='virement_detail'),

    # Prestataires
    path('prestataires/', views.prestataires_list, name='prestataires_list'),
    path('prestataires/creer/', views.prestataire_create, name='prestataire_create'),
    path('prestataires/<int:pk>/detail/', views.prestataire_detail, name='prestataire_detail'),
    path('prestataires/<int:pk>/modifier/', views.prestataire_edit, name='prestataire_edit'),
    path('prestataires/<int:pk>/supprimer/', views.prestataire_delete, name='prestataire_delete'),

    # Demandes d'achat
    path('demandes-achat/', views.da_list, name='da_list'),
    path('demandes-achat/creer/', views.da_create, name='da_create'),
    path('demandes-achat/<int:pk>/detail/', views.da_detail, name='da_detail'),
    path('demandes-achat/<int:pk>/modifier/', views.da_edit, name='da_edit'),
    path('demandes-achat/<int:pk>/en-etude/', views.da_en_etude, name='da_en_etude'),
    path('demandes-achat/<int:pk>/valider/', views.da_valider, name='da_valider'),
    path('demandes-achat/<int:pk>/refuser/', views.da_refuser, name='da_refuser'),
    path('demandes-achat/<int:da_pk>/solliciter/', views.offre_solliciter, name='offre_solliciter'),
    path('offres/<int:pk>/saisir/', views.offre_saisir, name='offre_saisir'),
    path('offres/<int:pk>/retenir/', views.offre_retenir, name='offre_retenir'),
    path('offres/<int:pk>/refuser/', views.offre_refuser, name='offre_refuser'),

    # Bons de commande
    path('bons-commande/', views.bc_list, name='bc_list'),
    path('bons-commande/creer/', views.bc_create, name='bc_create'),
    path('bons-commande/<int:pk>/pdf/', views.bc_pdf, name='bc_pdf'),
    path('bons-commande/<int:pk>/statut/<str:nouveau_statut>/', views.bc_change_statut, name='bc_change_statut'),
    path('bons-commande/<int:pk>/detail/', views.bc_detail, name='bc_detail'),
    path('bons-commande/<int:pk>/prolonger/', views.bc_prolong, name='bc_prolong'),
    path('bons-commande/<int:pk>/prolonger/page/', views.bc_prolonger_page, name='bc_prolonger_page'),
    path('bons-commande/<int:pk>/modifier/', views.bc_edit, name='bc_edit'),

    # Lignes budgétaires
    path('taches/<int:tache_pk>/lignes/creer/', views.ligne_budgetaire_create, name='ligne_budgetaire_create'),
    path('lignes/<int:pk>/modifier/', views.ligne_budgetaire_edit, name='ligne_budgetaire_edit'),
    path('lignes/<int:pk>/detail/', views.ligne_detail, name='ligne_detail'),
    path('lignes/<int:ligne_pk>/consommation/creer/', views.consommation_create, name='consommation_create'),

    # Bilans
    path('bilans/', views.bilans_view, name='bilans'),
    path('bilans/export/csv/', views.bilan_csv_export, name='bilan_csv_export'),
    path('bilans/export/pdf/', views.bilan_pdf_export, name='bilan_pdf_export'),

    # Journal de programmation par BC (imputations)
    path('journal-bc/', views.journal_bc_view, name='journal_bc'),

    # Journal de programmation (JP-BC : plan annuel des prestations)
    path('journal-programmation/', views.journal_list, name='journal_list'),
    path('journal-programmation/<int:pk>/creer-da/', views.journal_creer_da, name='journal_creer_da'),
    path('journal-programmation/creer/', views.prestation_create, name='prestation_create'),
    path('journal-programmation/<int:pk>/modifier/', views.prestation_edit, name='prestation_edit'),
    path('journal-programmation/<int:pk>/supprimer/', views.prestation_delete, name='prestation_delete'),

    # Pièces jointes
    path('pieces-jointes/upload/', views.piece_jointe_upload, name='piece_jointe_upload'),
    path('pieces-jointes/<int:pk>/supprimer/', views.piece_jointe_delete, name='piece_jointe_delete'),

    # Recherche globale
    path('recherche/', views.recherche_view, name='recherche'),

    # Journal
    path('journal/', views.journal_view, name='journal'),

    # Utilisateurs
    path('utilisateurs/', views.utilisateurs_list, name='utilisateurs_list'),
    path('utilisateurs/creer/', views.utilisateur_create, name='utilisateur_create'),
    path('utilisateurs/<int:pk>/detail/', views.utilisateur_detail, name='utilisateur_detail'),
    path('utilisateurs/<int:pk>/modifier/', views.utilisateur_edit, name='utilisateur_edit'),
    path('utilisateurs/<int:pk>/reinitialiser-mdp/', views.utilisateur_reset_pwd, name='utilisateur_reset_pwd'),
    path('utilisateurs/<int:pk>/toggle-actif/', views.utilisateur_toggle_actif, name='utilisateur_toggle_actif'),
    path('utilisateurs/<int:pk>/supprimer/', views.utilisateur_delete, name='utilisateur_delete'),

    # Paramètres
    path('parametres/', views.parametres_view, name='parametres'),

    # Notifications
    path('notifications/marquer-lues/', views.notifications_marquer_lues, name='notifications_marquer_lues'),

    # Exercices
    path('exercices/', views.exercices_list, name='exercices_list'),
    path('exercices/creer/', views.exercice_create, name='exercice_create'),
    path('exercices/<int:pk>/detail/', views.exercice_detail, name='exercice_detail'),
    path('exercices/<int:pk>/activer/', views.exercice_activer, name='exercice_activer'),
    path('exercices/<int:pk>/cloturer/', views.exercice_cloturer, name='exercice_cloturer'),
    path('exercices/<int:pk>/reconduire/', views.exercice_reconduire, name='exercice_reconduire'),
    path('exercices/<int:pk>/repertoire/', views.repertoire_sync, name='repertoire_sync'),
    # NB: les routes import-excel/template-excel ont été retirées (stubs non implémentés).
    path('exercice/switch/', views.exercice_switch, name='exercice_switch'),
    # Wizard création exercice
    path('exercices/wizard/step1/',  views.wizard_exercice_step1, name='wizard_exercice_step1'),
    path('exercices/wizard/step2/',  views.wizard_exercice_step2, name='wizard_exercice_step2'),
    path('exercices/wizard/step3/',  views.wizard_exercice_step3, name='wizard_exercice_step3'),
    path('exercices/wizard/step4/',  views.wizard_exercice_step4, name='wizard_exercice_step4'),
    path('exercices/wizard/cancel/', views.wizard_exercice_cancel, name='wizard_exercice_cancel'),
    # Annulations admin
    # Module Consommations directes
    path('consommations/', views.consommations_list, name='consommations_list'),
    path('consommations/creer/', views.consommation_create_module, name='consommation_create_module'),
    path('consommations/<int:pk>/modifier/', views.consommation_edit, name='consommation_edit'),
    path('consommations/<int:pk>/annuler/', views.annuler_consommation_directe, name='annuler_consommation_directe'),
    path('virements/<int:pk>/annuler/', views.annuler_virement, name='annuler_virement'),

    # RGPD (Sprint 3)
    path('rgpd/export/', views.rgpd_export_view, name='rgpd_export'),
]
