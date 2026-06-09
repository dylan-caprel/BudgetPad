# Audit technique — BudgetPAD

> Revue d'architecture et de qualité de code, menée selon une approche d'ingénieur senior
> découvrant le codebase. Objectif : **améliorer qualité / scalabilité / maintenabilité
> sans changer le comportement fonctionnel**.
>
> Port Autonome de Douala — Direction des Ressources Humaines.

---

## 1. Architecture rétro-conçue (flux réel)

```
Requête HTTP
  → core/urls.py (~125 routes, inclus à la racine de budgetpad/urls.py)
  → core/views.py (83 vues, décorées @login_required puis @role_required)
  → [parfois] core/services/*.py (8 services métier)
  → core/models.py (22 modèles + QuerySets annotés)
  → MySQL / MariaDB
  → Templates (49 fichiers, Bootstrap 5, rendu côté serveur)

Transverse : middleware de changement de mot de passe forcé ;
authentification via modèle Utilisateur custom (champ `role`).
```

### Domaines métier

| Domaine          | Modèles                                                        | Règles clés                         |
|------------------|---------------------------------------------------------------|-------------------------------------|
| Budget (arbre)   | Exercice → Tâche → LigneBudgétaire                            | R7 : un seul exercice actif         |
| Achat            | DemandeAchat → Offre → BonCommande → LigneBC + ImputationBC   | machines à états `peut_transiter_vers()` |
| Dépense directe  | ConsommationDirecte                                           | R11 : avis CAPRI obligatoire        |
| Transferts       | VirementBudgetaire                                            | source → destination, contrôle solde|
| Planning         | PrestationProgrammee                                          | journal de programmation (JP-BC)    |
| Transverse       | PieceJointe (polymorphe), JournalActivite (chaîne SHA-256), Sequence (numérotation atomique) | — |

### Points déjà solides (à préserver)

- **`with_aggregates()` via sous-requêtes corrélées** (`_sum_subquery`, `models.py:148`) :
  évite le piège du produit cartésien Django lors de l'agrégation de plusieurs relations
  multi-valuées. Correct et non trivial.
- **Sécurité prod** (`settings/prod.py`) : `SECRET_KEY` depuis l'environnement (échoue si absent),
  `DEBUG=False`, HSTS, `SECURE_SSL_REDIRECT`, cookies `Secure`, `nosniff`, referrer-policy.
- **Aucun SQL brut** → pas de surface d'injection ; tout passe par l'ORM.
- Couche service présente, journal d'audit haché, numérotation atomique, **65 tests** verts.

---

## 2. Problèmes critiques (avec preuves)

### C1 — `views.py` monolithe 🔴
3 565 lignes, 83 vues dans un seul fichier. `bc_create` fait **157 lignes** (`views.py:929`).
Impact : navigation, revue, et conflits de merge difficiles.

### C2 — Logique métier dans les vues 🔴
**15 blocs `transaction.atomic` dans `views.py`** contre 12 dans les services.
`DemandeAchatService.creer()` existe, mais `bc_create`, les virements et les consommations
implémentent leur logique transactionnelle **directement dans la vue**. L'invariant
« toute mutation passe par un service » n'est pas tenu de façon cohérente.

### C3 — Duplication de logique 🟠

| Logique dupliquée                                   | Emplacements                          |
|-----------------------------------------------------|---------------------------------------|
| Vérification de solde (`with_aggregates().get()` + comparaison + message) | `views.py` 2436, 2561, 2626, 3065 (×4) |
| Résolution de période                               | `_get_periode_filter` (175) **et** `_resolve_bilan_periode` (1186) |
| « consommation = BC + consommations directes »      | `dashboard_view` (216) **et** `bilans_view` (1276) |

> La 3ᵉ duplication a provoqué un **bug réel** : le bilan ignorait les consommations directes
> (corrigé). La duplication est une fabrique à régressions.

### C4 — Scalabilité / indexation DB 🟠
22 modèles, 34 clés étrangères, mais **~4 `db_index` explicites** seulement.
Champs filtrés en permanence sans index dédié : `statut`, `reference`, `numero`, `date_emission` ;
aucun index composite `(exercice, statut)`. Acceptable à l'échelle actuelle, risque si volumétrie ×100.

### C5 — Maintenabilité 🟡
- **Imports locaux** dispersés (`from datetime import …` dans plusieurs vues) au lieu du niveau module.
- **`_exercice_courant()` appelé 15×** manuellement — devrait être un *context processor* /
  attribut `request.exercice`.
- **Chaînes magiques** (`'cree'`, `'admin'`, `'annule'`…) éparpillées alors que `core/constants.py` existe.
- **PieceJointe polymorphe** (`type_entite` + `entite_id`, sans vraie FK) : pas d'intégrité
  référentielle ni de cascade DB. Choix assumé — à documenter explicitement.

---

## 3. Stratégie de refactoring (priorisée)

| #  | Action                                                            | Impact                          | Risque  | Effort  |
|----|-------------------------------------------------------------------|---------------------------------|---------|---------|
| R1 | Extraire la **vérif de solde** dans `BudgetService`               | Supprime 4 duplications + 1 bug | Faible  | ~1 h    |
| R2 | Unifier les **2 résolveurs de période**                           | Cohérence dashboard/bilan       | Faible  | ~1 h    |
| R3 | « consommation = BC + directes » → **une seule fonction**         | Anti-régression bilan           | Faible  | ~30 min |
| R4 | Découper `views.py` en **package `views/`** par domaine           | Lisibilité, merges              | Moyen   | 2-3 h   |
| R5 | Déplacer `bc_create` / virement / conso vers les **services**     | Cohérence d'architecture        | Moyen   | 3-4 h   |
| R6 | Ajouter des **index** (`Meta.indexes` composites)                 | Scalabilité                     | Faible  | ~1 h    |
| R7 | `request.exercice` via **context processor**                      | -15 répétitions                 | Faible  | ~1 h    |

---

## 4. Code production-grade (exemples)

### R1 — point de vérité unique pour le solde

```python
# core/services/budget_service.py  (nouveau)
from decimal import Decimal
from ..models import LigneBudgetaire


class SoldeInsuffisant(ValueError):
    def __init__(self, ligne, montant, disponible):
        self.ligne, self.montant, self.disponible = ligne, montant, disponible
        super().__init__(
            f"Solde insuffisant sur {ligne.code_nature}. "
            f"Disponible : {disponible:,.0f} FCFA"
        )


class BudgetService:
    @staticmethod
    def solde_disponible(ligne_id: int, exclure_conso_id: int | None = None) -> Decimal:
        """Solde réel d'une ligne, en réintégrant une consommation en cours d'édition."""
        ligne = LigneBudgetaire.objects.with_aggregates().get(pk=ligne_id)
        dispo = ligne.solde
        if exclure_conso_id:
            from ..models import ConsommationDirecte
            ancienne = (ConsommationDirecte.objects
                        .filter(pk=exclure_conso_id, est_annule=False)
                        .values_list('montant', flat=True).first())
            dispo += ancienne or Decimal('0')
        return dispo

    @classmethod
    def assert_solde(cls, ligne, montant, exclure_conso_id=None):
        dispo = cls.solde_disponible(ligne.pk, exclure_conso_id)
        if montant > dispo:
            raise SoldeInsuffisant(ligne, montant, dispo)
        return dispo
```

```python
# dans la vue — remplace les ~8 lignes répétées (×4) :
try:
    BudgetService.assert_solde(ligne, montant, exclure_conso_id=conso.pk)
except SoldeInsuffisant as e:
    messages.error(request, str(e))
    return redirect('consommations_list')
```

### R4 — découpage de `views.py` (déplacements purs, zéro changement fonctionnel)

```
core/views/
  __init__.py        # ré-exporte tout : from .achat import *  (urls.py inchangé)
  _helpers.py        # _exercice_courant, log_action, role_required, périodes
  dashboard.py       # dashboard_view, bilans_view
  taches.py          # tâches + lignes budgétaires
  achat.py           # da_*, offre_*, bc_*
  consommation.py    # consommation_*, virement_*
  journal.py         # journal_*, prestation_*
  exercice.py        # exercice_*, wizard_*
  admin.py           # utilisateurs, paramètres, rgpd
```

### R6 — index de scalabilité (migration seule, aucune logique)

```python
class Meta:
    indexes = [
        models.Index(fields=['exercice', 'statut']),   # bc_list, da_list
        models.Index(fields=['reference']),            # recherche DA
        models.Index(fields=['date_emission']),        # filtres de période
    ]
```

---

## 5. Verdict

BudgetPAD n'est **pas** un codebase legacy : le cœur (agrégats, sécurité, audit, tests) est de
bon niveau. Les vrais axes d'amélioration sont la **dette de structure** (`views.py` monolithe +
logique hors couche service) et la **duplication** (solde, période, consommation) — précisément
ce qui a généré le bug du bilan.

**Aucune des améliorations proposées ne modifie le comportement** : ce sont des extractions et
des déplacements, couverts par la suite de 65 tests. Ordre d'application recommandé :
**R1 → R3 → R2 → R6** (faible risque), puis **R7 → R4 → R5** (structurels).
