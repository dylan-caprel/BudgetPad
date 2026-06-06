"""Constantes métier du projet BudgetPAD"""

from decimal import Decimal

# ===== FISCAL =====
TVA_RATE = Decimal('19.25')  # Taux TVA Cameroun

# ===== SEUILS D'ALERTE =====
ALERTE_SEUIL_WARNING = 70    # 70% -> Warning
ALERTE_SEUIL_DANGER = 90     # 90% -> Danger

# ===== COULEURS UI =====
TAUX_COLORS = {
    'success': '#1A5632',    # < 70%
    'warning': '#F39C12',    # 70-89%
    'danger': '#E74C3C',     # >= 90%
}

# ===== RÔLES & PERMISSIONS =====
# Note : 'dag' supprimé — l'outil est utilisé UNIQUEMENT par la DRH.
ROLES_LECTEUR_ONLY = ['lecteur']
ROLES_EDITEUR = ['directeur_drh', 'assistante_drh', 'chef_service', 'admin']
ROLES_VALIDEUR = ['directeur_drh', 'admin']
ROLES_ADMIN = ['admin']

# ===== STATUTS AVEC METADATA =====
STATUT_METADATA = {
    'cree': {
        'label': 'Créé',
        'color': 'secondary',
        'editable': True,
        'deletable': True,
    },
    'notifie': {
        'label': 'Notifié',
        'color': 'info',
        'editable': True,
        'deletable': False,
    },
    'en_cours': {
        'label': 'En cours',
        'color': 'primary',
        'editable': False,
        'deletable': False,
    },
    'execute': {
        'label': 'Exécuté',
        'color': 'success',
        'editable': False,
        'deletable': False,
    },
    'annule': {
        'label': 'Annulé',
        'color': 'danger',
        'editable': False,
        'deletable': False,
    },
}

# ===== DA STATUTS =====
DA_STATUT_METADATA = {
    'cree': {'label': 'Créée', 'color': 'secondary'},
    'en_etude': {'label': 'Transmise DAG', 'color': 'warning'},
    'validee': {'label': 'Validée', 'color': 'success'},
    'bc_cree': {'label': 'BC créé', 'color': 'info'},
    'annulee': {'label': 'Annulée', 'color': 'danger'},
}

# ===== ACTIONS LOG =====
LOG_ACTIONS = {
    'DA.create': 'Création DA',
    'DA.validate': 'Validation DA',
    'DA.refuse': 'Refus DA',
    'BC.create': 'Création BC',
    'BC.notify': 'Notification BC',
    'BC.execute': 'Exécution BC',
    'BC.cancel': 'Annulation BC',
    'Virement': 'Virement',
    'Tache.create': 'Création tâche',
    'Tache.edit': 'Modification tâche',
}
