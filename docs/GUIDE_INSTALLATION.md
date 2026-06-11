# Guide d'installation — BudgetPAD

> Outil de suivi budgétaire de la Direction des Ressources Humaines
> du Port Autonome de Douala (PAD).
>
> **Stack** : Python 3.12+ (3.14 recommandé) · Django 6 · MySQL/MariaDB · Bootstrap 5
> **Dépôt** : https://github.com/dylan-caprel/BudgetPad

Ce guide couvre deux situations :

- **[Cas A](#cas-a--installer-depuis-le-dossier-transféré)** — vous avez reçu le **dossier du
  projet par transfert de fichiers** (clé USB, archive ZIP, partage réseau…)
  *(cas le plus courant — commencez ici)* ;
- **[Cas B](#cas-b--installer--mettre-à-jour-via-git)** — installation ou mise à jour **via Git**
  (recommandé pour récupérer les futures mises à jour).

---

## Cas A — Installer depuis le dossier transféré

Vous avez reçu le dossier complet du projet (ex. `budgetpad/`). Ce dossier contient le code
à jour **mais aussi des fichiers propres à la machine d'origine** qu'il faut remplacer.

> ℹ️ **Si vous aviez déjà une ancienne version de BudgetPAD** : votre base de données
> n'est PAS dans le dossier — elle vit dans votre serveur MySQL. Le nouveau dossier
> s'y reconnectera (étape A.4) et mettra son schéma à niveau (étape A.5).
> Vous pouvez archiver/supprimer l'ancien dossier du projet, il ne servira plus.

### A.1 — Prérequis

| Logiciel | Version | Vérification |
|---|---|---|
| Python | 3.12 minimum (3.14 recommandé) | `python --version` |
| MySQL **ou** MariaDB | 8.0+ / 10.6+ (déjà installé si vous aviez l'ancienne version) | `mysql --version` |

### A.2 — Placer le dossier et NETTOYER l'environnement transféré

Copiez le dossier où vous voulez (ex. `C:\Projets\budgetpad`), puis **supprimez
impérativement le dossier `env/`** s'il est présent dans le transfert :

```powershell
cd C:\Projets\budgetpad        # adaptez le chemin
Remove-Item -Recurse -Force env
```

> ⚠️ **Pourquoi ?** Un environnement virtuel Python n'est **pas portable** : ses scripts
> contiennent des chemins absolus de la machine d'origine
> (`C:\Users\User\Desktop\budgetpad\env\...`). S'il n'est pas recréé, vous aurez des
> erreurs du type *« Unable to create process »* ou un Python introuvable.

### A.3 — Créer un environnement virtuel PROPRE + dépendances

```powershell
python -m venv env
.\env\Scripts\Activate.ps1     # PowerShell  (ou env\Scripts\activate.bat en cmd)

pip install -r requirements.txt
```

### A.4 — Adapter le fichier `.env` à VOTRE machine

Le transfert contient probablement le `.env` de la machine d'origine — **il pointe vers
le MySQL du développeur, pas le vôtre**. Ouvrez `.env` à la racine du projet et adaptez :

```ini
SECRET_KEY=<laissez la valeur existante, ou regénérez-en une>
DEBUG=True
DJANGO_ENV=dev
ALLOWED_HOSTS=localhost,127.0.0.1

DB_ENGINE=django.db.backends.mysql
DB_NAME=budgetpad
DB_USER=root
DB_PASSWORD=<VOTRE mot de passe MySQL>     ← à changer
DB_HOST=localhost
DB_PORT=3306                               ← 3306 en général ; 3307 avec certains XAMPP/WAMP
```

> 💡 Si `.env` est absent du transfert : `copy .env.example .env` puis remplissez les
> mêmes champs. Pour générer une SECRET_KEY :
> ```powershell
> python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
> ```

**Si vous n'avez pas encore la base** (première installation sur cette machine),
créez-la dans un client MySQL :

```sql
CREATE DATABASE budgetpad CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

### A.5 — Mettre la base à niveau (migrations)

Que votre base soit ancienne (version précédente de l'outil) ou neuve :

```powershell
python manage.py migrate
```

Vérification — toutes les lignes doivent être cochées `[X]`, jusqu'à `0013` :

```powershell
python manage.py showmigrations core
# ...
# [X] 0012_prestation_programmee
# [X] 0013_boncommande_idx_bc_date_emission_and_more
```

### A.6 — Charger les données réelles 2026

Les données officielles de la DRH (PDF « Suivi détaillé des tâches » + Excel
« JP-BC DRH 2026 ») sont embarquées dans le projet :

```powershell
python manage.py seed_real_data --reset
```

| Option | Effet |
|---|---|
| `--reset` | **Recommandé** : supprime les DA/BC de démonstration et les tâches de test de l'ancienne version, puis charge l'état officiel pur |
| *(sans option)* | Upsert : met à jour l'exercice 2026 sans toucher au reste |
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

### A.7 — Lancer l'application

```powershell
python manage.py runserver
```

→ http://127.0.0.1:8000 — connectez-vous (voir [comptes](#comptes-de-démonstration)).

### A.8 — (Optionnel) Vérifier que tout fonctionne

```powershell
python manage.py check        # doit afficher : 0 issues
pytest                        # doit afficher : 65 passed
```

---

## Cas B — Installer / mettre à jour via Git

Recommandé pour recevoir les **futures mises à jour** sans nouveau transfert de fichiers.

### Première installation

```powershell
git clone https://github.com/dylan-caprel/BudgetPad.git budgetpad
cd budgetpad
python -m venv env
.\env\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # puis éditez .env (cf. étape A.4)
python manage.py migrate
python manage.py seed_real_data
python manage.py runserver
```

### Mises à jour ultérieures

```powershell
git pull origin main
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

> 💡 Si les dernières évolutions ne sont pas encore fusionnées dans `main`,
> utilisez la branche de travail :
> `git checkout refactor/lignes-budgetaires-et-audit-complet && git pull`

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
| `Unable to create process using ...\env\Scripts\python.exe` ou Python introuvable | Venv transféré depuis l'autre machine (chemins absolus) | Supprimez `env/` et recréez-le (étape A.2 / A.3) |
| `ValueError: SECRET_KEY must be set in .env file` | `.env` manquant ou incomplet | Créez `.env` depuis `.env.example` et renseignez `SECRET_KEY` |
| `OperationalError (1045)` — access denied | Mot de passe MySQL du `.env` = celui de l'autre machine | Mettez **votre** mot de passe dans `DB_PASSWORD` (étape A.4) |
| `OperationalError (2003)` — can't connect | MySQL arrêté ou mauvais port | Démarrez MySQL ; vérifiez `DB_PORT` (3306 par défaut, parfois 3307 avec XAMPP/WAMP) |
| `OperationalError (1049)` — unknown database | Base non créée sur cette machine | Exécutez le `CREATE DATABASE` de l'étape A.4 |
| `OperationalError: Unknown column ...` au démarrage | Migrations non appliquées | `python manage.py migrate` |
| Erreur d'installation de `mysqlclient` (Windows) | Compilateur C absent | `pip install mysqlclient --only-binary :all:` ou installez « Microsoft C++ Build Tools » |
| Accents mal affichés dans la console Windows | Encodage console | Lancez avec `python -X utf8 manage.py ...` |
| Page de connexion en boucle | Cookies d'une ancienne session | Videz les cookies du site (Ctrl+Maj+Suppr) |
| Mot de passe refusé après le seed | Comptes resynchronisés | Tous les mots de passe sont réinitialisés à `Pad2025@` |

---

## Support

- **Développeur** : Dylan Caprel Ngando — doumbedylanng@gmail.com
- **Documentation projet** : dossier [`docs/`](.) (diagramme de classes, audit technique)
