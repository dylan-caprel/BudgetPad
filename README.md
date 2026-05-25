# BudgetPAD

Application Django de suivi budgétaire et de gestion des achats pour la
**Direction des Ressources Humaines** du Port Autonome de Douala (PAD).

## Fonctionnalités

- Suivi d'un exercice budgétaire annuel (dotation + virements)
- Gestion de tâches budgétaires (codes nature, taux de consommation, alertes)
- Virements inter-tâches (atomiques, avec audit)
- Demandes d'achat → offres prestataires → bons de commande
- Workflow de validation : Assistante DRH → Directeur DRH → DAG
- Calcul automatique TVA 19,25 %
- Journal d'activité immuable + historique de statuts
- Notifications utilisateur (badge dynamique)
- Tableau de bord + bilans graphiques

## Stack technique

- **Backend** : Django 6.0, Python 3.14
- **Base de données** : MySQL 8 (UTF-8 mb4)
- **Frontend** : Bootstrap 5, Chart.js, Bootstrap Icons
- **Sécurité** : django-axes (anti brute-force), middleware force password change
- **Outils** : django-filter, pytest, factory_boy

## Installation

```powershell
# 1. Cloner et créer un environnement virtuel
python -m venv env
.\env\Scripts\Activate.ps1

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Créer le fichier .env à la racine
@"
SECRET_KEY=changez-moi-en-une-cle-aleatoire-50-caracteres
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DJANGO_ENV=dev

DB_ENGINE=django.db.backends.mysql
DB_NAME=budgetpad
DB_USER=root
DB_PASSWORD=
DB_HOST=localhost
DB_PORT=3306
"@ | Out-File -Encoding utf8 .env

# 4. Créer la base et appliquer les migrations
# (Sous MySQL : CREATE DATABASE budgetpad CHARACTER SET utf8mb4;)
python manage.py migrate

# 5. Charger les données de démonstration
python manage.py seed_data

# 6. Lancer le serveur
python manage.py runserver
```

Accès : http://127.0.0.1:8000/login/

## Comptes de démonstration

Tous les comptes ont le mot de passe initial **`pad2025`** et doivent le
changer à la première connexion (flag `must_change_password=True`).

| Username | Rôle | Permissions |
|---|---|---|
| `admin` | Administrateur | Tout |
| `directeur` | Directeur DRH | Création DA, virements |
| `assistante` | Assistante DRH | Tâches, DA, virements |
| `dag` | DAG | Valide/refuse DA, crée et transitionne BC |
| `lecteur` | Auditeur | Lecture seule |

## Architecture

```
budgetpad/
├── budgetpad/
│   ├── settings/
│   │   ├── __init__.py     # bascule dev/prod via DJANGO_ENV
│   │   ├── base.py
│   │   ├── dev.py
│   │   ├── prod.py
│   │   └── test.py         # SQLite en mémoire
│   ├── urls.py
│   └── wsgi.py
├── core/
│   ├── models.py           # 11 modèles + TacheQuerySet annoté
│   ├── views.py            # 22 FBV
│   ├── forms.py
│   ├── filters.py          # django-filter FilterSets
│   ├── middleware.py       # ForcePasswordChangeMiddleware
│   ├── mixins.py           # RoleRequiredMixin (pour futures CBV)
│   ├── context_processors.py
│   ├── services/
│   │   ├── sequence_service.py      # Numérotation atomique
│   │   ├── bon_commande_service.py  # Création + transitions BC
│   │   ├── demande_achat_service.py # Création DA + notifications
│   │   ├── virement_service.py      # Virement avec select_for_update
│   │   ├── tache_service.py
│   │   └── notification_service.py
│   ├── templatetags/core_tags.py    # has_role, in_csv
│   ├── management/commands/seed_data.py
│   └── tests/                       # pytest + factory_boy
├── templates/
│   ├── base.html                    # Squelette
│   ├── partials/                    # _sidebar, _topbar, _messages, _pagination...
│   ├── core/                        # Pages applicatives
│   └── registration/
├── static/css/budgetpad.css
└── logs/                            # rotating files (budgetpad.log, security.log)
```

## Tests

```powershell
.\env\Scripts\python.exe -m pytest
```

37 tests couvrent les services critiques (Sequence, BonCommande, DemandeAchat,
Virement) et les annotations de QuerySet sur Tache.

## Commandes utiles

```powershell
# Reset des verrouillages axes
.\env\Scripts\python.exe manage.py axes_reset

# Recharger les données de démo
.\env\Scripts\python.exe manage.py seed_data

# Mode production (settings.prod)
$env:DJANGO_ENV='prod'; .\env\Scripts\python.exe manage.py check --deploy
```

## Logs

- `logs/budgetpad.log` — applicatif (5 Mo × 5)
- `logs/security.log` — authentification (5 Mo × 10)

## Statut du projet

- Sprint 0 ✅ — hotfixes critiques (CSRF, bug `creee`, mots de passe forcés)
- Sprint 1 ✅ — fiabilité (atomicité, services, annotations QuerySet, logging, axes)
- Sprint 2 ✅ — qualité (pagination, filtres, partials, tests automatisés)
- Sprint 3 ⏳ — production (Celery, PDF des BC, monitoring, archivage)
