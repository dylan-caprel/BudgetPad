# Guide d'installation — BudgetPAD

> Outil de suivi budgétaire de la Direction des Ressources Humaines
> du Port Autonome de Douala (PAD).
>
> **Stack** : Python 3.12+ (3.14 recommandé) · Django 6 · MySQL/MariaDB · Bootstrap 5
> **Dépôt** : https://github.com/dylan-caprel/BudgetPad

Ce guide couvre deux situations :

- **[Cas A](#cas-a--mettre-à-jour-une-installation-existante)** — vous avez **déjà installé une
  ancienne version** de BudgetPAD et vous voulez récupérer les mises à jour récentes
  *(cas le plus courant — commencez ici)* ;
- **[Cas B](#cas-b--installation-complète-depuis-zéro)** — installation **complète depuis zéro**
  sur une machine vierge.

---

## Cas A — Mettre à jour une installation existante

Votre machine a déjà : le dépôt cloné, un environnement virtuel, MySQL configuré et
l'application qui démarrait. Il suffit de récupérer le code, mettre à jour les
dépendances, appliquer les nouvelles migrations et recharger les données officielles.

### A.1 — Récupérer le code à jour

Ouvrez un terminal (PowerShell ou cmd) **dans le dossier du projet** :

```bash
git fetch origin
git checkout main
git pull origin main
```

> 💡 Si les dernières mises à jour ne sont pas encore fusionnées dans `main`
> (PR en attente), utilisez la branche de travail :
> ```bash
> git checkout refactor/lignes-budgetaires-et-audit-complet
> git pull origin refactor/lignes-budgetaires-et-audit-complet
> ```

### A.2 — Mettre à jour les dépendances

```bash
# Activer l'environnement virtuel existant
env\Scripts\activate          # Windows
# source env/bin/activate     # Linux/macOS

pip install -r requirements.txt
```

### A.3 — Vérifier le fichier `.env`

Votre `.env` existant reste valable. Vérifiez simplement qu'il contient bien :

```ini
SECRET_KEY=<votre clé>        # OBLIGATOIRE — l'app refuse de démarrer sans
DEBUG=True
DJANGO_ENV=dev
DB_NAME=budgetpad
DB_USER=root
DB_PASSWORD=<votre mot de passe MySQL>
DB_HOST=localhost
DB_PORT=3306                  # adaptez si votre MySQL écoute ailleurs (ex. 3307)
```

### A.4 — Appliquer les nouvelles migrations

L'ancienne version s'arrêtait vers la migration 0006. Les versions récentes ajoutent
les migrations **0007 → 0013** (format réel PAD, CAPRI, pièces jointes, journal de
programmation, index de performance) :

```bash
python manage.py migrate
```

Vérification :

```bash
python manage.py showmigrations core
# Toutes les lignes doivent être cochées [X], jusqu'à :
# [X] 0013_boncommande_idx_bc_date_emission_and_more
```

### A.5 — Charger les données réelles 2026

Les données officielles de la DRH (PDF « Suivi détaillé des tâches » + Excel
« JP-BC DRH 2026 ») sont embarquées dans le dépôt. Pour remettre la base dans
l'état officiel :

```bash
python manage.py seed_real_data --reset
```

| Option | Effet |
|---|---|
| *(sans option)* | Upsert : met à jour l'exercice 2026 sans toucher au reste (relançable sans doublon) |
| `--reset` | **Recommandé** : supprime les DA/BC de démonstration et les tâches de test, puis recharge l'état officiel pur |
| `--flush` | ⚠️ Vide **toute** la base avant de recharger |

Résultat attendu :

```
Seed reel PAD 2026 termine :
  - Exercice 2026 actif (budget global 6 727 266 993 FCFA)
  - 58 taches / 130 lignes budgetaires
  - 15 virements (transferts reconstitues)
  - 40 consommations directes (1 692 877 445 FCFA)
  - 36 prestations au journal (36 liees a une ligne)
  - 5 comptes (mot de passe : Pad2025@)
```

### A.6 — Lancer l'application

```bash
python manage.py runserver
```

→ http://127.0.0.1:8000 — connectez-vous (voir [comptes](#comptes-de-démonstration)).

### A.7 — (Optionnel) Vérifier que tout fonctionne

```bash
python manage.py check        # doit afficher : 0 issues
pytest                        # doit afficher : 65 passed
```

---

## Cas B — Installation complète depuis zéro

### B.1 — Prérequis

| Logiciel | Version | Téléchargement |
|---|---|---|
| Python | 3.12 minimum (3.14 recommandé) — cochez **« Add to PATH »** | https://www.python.org/downloads/ |
| MySQL **ou** MariaDB | 8.0+ / 10.6+ | https://dev.mysql.com/downloads/ ou https://mariadb.org/download/ |
| Git | dernière version | https://git-scm.com/downloads |

### B.2 — Cloner le projet

```bash
git clone https://github.com/dylan-caprel/BudgetPad.git budgetpad
cd budgetpad
```

### B.3 — Environnement virtuel + dépendances

```bash
python -m venv env
env\Scripts\activate          # Windows
# source env/bin/activate     # Linux/macOS

pip install -r requirements.txt
```

### B.4 — Créer la base de données

Dans un client MySQL (ligne de commande, Workbench ou phpMyAdmin) :

```sql
CREATE DATABASE budgetpad CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### B.5 — Configurer l'environnement

```bash
copy .env.example .env        # Windows   (cp .env.example .env sur Linux/macOS)
```

Puis éditez `.env` :

```ini
SECRET_KEY=générez-une-chaîne-aléatoire-de-50-caractères-minimum
DEBUG=True
DJANGO_ENV=dev
ALLOWED_HOSTS=localhost,127.0.0.1

DB_ENGINE=django.db.backends.mysql
DB_NAME=budgetpad
DB_USER=root
DB_PASSWORD=<votre mot de passe MySQL>
DB_HOST=localhost
DB_PORT=3306
```

> 🔑 Pour générer une SECRET_KEY :
> ```bash
> python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
> ```

### B.6 — Migrations + données + lancement

```bash
python manage.py migrate
python manage.py seed_real_data
python manage.py runserver
```

→ http://127.0.0.1:8000

---

## Comptes de démonstration

Créés automatiquement par `seed_real_data` — mot de passe unique : **`Pad2025@`**

| Identifiant | Rôle | Droits principaux |
|---|---|---|
| `admin` | Administrateur | Tout (édition globale, annulations, utilisateurs, paramètres) |
| `directeur` | Directeur DRH | Validation des DA, virements |
| `chef` | Chef de service | Création/suivi DA |
| `assistante` | Assistante DRH | Saisie DA, consommations |
| `lecteur` | Lecteur | Consultation seule |

---

## Nouveautés depuis l'ancienne version

| Module | Nouveauté |
|---|---|
| **Format réel PAD** | Numéros `DAC{AAMM}DLA{NNNNN}` / `STD{AAMM}DLA{NNNNN}`, délai en semaines, articles de BC, PDF officiel |
| **CAPRI (R11)** | N° + date d'avis CAPRI obligatoires sur BC et consommations directes (badge « à régulariser » pour l'historique) |
| **Workflow DA** | Statuts simplifiés : Créée → Transmise DAG → Validée → BC créé / Annulée ; validation conditionnée à une pièce jointe (proforma ou DA signée) |
| **Journal de programmation** | Nouveau module (menu latéral) : plan annuel JP-BC, 36 prestations réelles, bouton « Créer DA » depuis une prestation, CRUD admin |
| **Consommations directes** | Nouveau module dédié : liste + KPI, offcanvas détail **éditable par l'admin**, création avec pièce jointe, annulation motivée |
| **Données réelles 2026** | 58 tâches / 130 lignes / transferts / consommations fidèles au suivi officiel (vérifié à 0 écart) |
| **Bilan corrigé** | La consommation globale intègre BC **et** consommations directes |
| **Pièces jointes** | Multi-PJ par entité, titres personnalisés, validation taille/type/contenu |
| **Performance** | 9 index de base de données, suppression de requêtes N+1 |

---

## Dépannage

| Problème | Cause | Solution |
|---|---|---|
| `ValueError: SECRET_KEY must be set in .env file` | `.env` manquant ou incomplet | Créez `.env` depuis `.env.example` et renseignez `SECRET_KEY` |
| `django.db.utils.OperationalError (2003)` — can't connect | MySQL arrêté ou mauvais port | Démarrez MySQL ; vérifiez `DB_PORT` (3306 par défaut, parfois 3307 avec XAMPP/WAMP) |
| `OperationalError (1049)` — unknown database | Base non créée | Exécutez le `CREATE DATABASE` de l'étape B.4 |
| `OperationalError: Unknown column ...` au démarrage | Migrations non appliquées | `python manage.py migrate` |
| Erreur d'installation de `mysqlclient` (Windows) | Compilateur C absent | `pip install mysqlclient` utilise des roues précompilées sur Python récents ; sinon installez « Microsoft C++ Build Tools » ou utilisez `pip install mysqlclient --only-binary :all:` |
| Accents mal affichés dans la console Windows | Encodage console | Lancez avec `python -X utf8 manage.py ...` |
| Page de connexion en boucle | Cookies d'une ancienne session | Videz les cookies du site (Ctrl+Maj+Suppr) |
| Mot de passe refusé après mise à jour | Comptes resynchronisés par le seed | Tous les mots de passe sont réinitialisés à `Pad2025@` |

---

## Support

- **Développeur** : Dylan Caprel Ngando — doumbedylanng@gmail.com
- **Documentation projet** : dossier [`docs/`](.) (diagramme de classes, audit technique)
