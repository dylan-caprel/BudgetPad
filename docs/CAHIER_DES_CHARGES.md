# Cahier des charges — BudgetPAD

**Application de suivi budgétaire et de gestion des achats**
Direction des Ressources Humaines — Port Autonome de Douala (PAD)

| | |
|---|---|
| **Version** | 1.0 — état actuel de l'application (juin 2026) |
| **Maîtrise d'ouvrage** | Direction des Ressources Humaines du PAD |
| **Encadrement** | Abdul Aziz Njikam Nfomou |
| **Réalisation** | Dylan Caprel Ngando |
| **Dépôt** | https://github.com/dylan-caprel/BudgetPad |

---

## 1. Objet du document

Le présent cahier des charges décrit les besoins fonctionnels et non fonctionnels couverts
par l'application **BudgetPAD** dans son état actuel. Il sert de référence contractuelle et
académique : périmètre, acteurs, exigences, règles de gestion, architecture, données
reprises, critères de recette et évolutions prévues.

---

## 2. Contexte et problématique

### 2.1 Contexte

Le **Port Autonome de Douala (PAD)** est l'autorité portuaire du port de Douala-Bonabéri,
principal port du Cameroun. Sa **Direction des Ressources Humaines (DRH)** gère un budget
annuel de fonctionnement et d'investissement réparti en **tâches budgétaires** (activités)
elles-mêmes décomposées en **lignes budgétaires** (codes nature comptables).

L'exécution de ce budget passe par deux canaux :
- la **chaîne d'achat** : journal de programmation → demande d'achat (DA) → consultation
  de prestataires (offres) → bon de commande (BC) → imputation budgétaire ;
- les **consommations directes** (dépenses sans bon de commande : achats directs,
  assistance sociale, urgences), soumises à l'avis préalable **CAPRI** de la DCG.

### 2.2 Problématique

Avant BudgetPAD, le suivi reposait sur des documents bureautiques dispersés
(classeurs Excel « JP-BC », états PDF « Suivi détaillé des tâches », courriers) :

- pas de vision consolidée en temps réel des soldes et taux de consommation ;
- ressaisies multiples et risque d'écart entre le journal, les DA, les BC et le suivi ;
- contrôles manuels des règles métier (solde disponible, avis CAPRI, exercice clôturé) ;
- absence de traçabilité opposable des actions (qui a validé quoi, quand) ;
- consolidation laborieuse pour les bilans périodiques et annuels.

### 2.3 Solution retenue

Une application web interne mono-direction (DRH), centralisant le référentiel budgétaire,
la chaîne d'achat au **format réel des documents PAD**, les contrôles automatiques des
règles de gestion et la restitution (tableaux de bord, bilans, exports).

---

## 3. Objectifs

| # | Objectif | Indicateur de réussite |
|---|---|---|
| O1 | Centraliser le référentiel budgétaire (exercices, tâches, lignes) | Reprise des données réelles 2026 sans écart |
| O2 | Dématérialiser la chaîne d'achat DA → Offres → BC au format PAD | Numérotation `DAC{AAMM}DLA{NNNNN}` / `STD{AAMM}DLA{NNNNN}`, PDF de BC conforme |
| O3 | Fiabiliser l'exécution par des contrôles automatiques | Blocage solde insuffisant, CAPRI obligatoire, exercice verrouillé |
| O4 | Garantir la traçabilité | Journal d'activité immuable chaîné SHA-256 |
| O5 | Restituer l'information décisionnelle | Tableau de bord, bilans périodiques, exports CSV/PDF |
| O6 | Sécuriser les accès | Rôles, anti-force brute, changement de mot de passe forcé |

---

## 4. Périmètre

### 4.1 Inclus (état actuel)

- Gestion des **exercices budgétaires** : création (assistant en 4 étapes), activation
  exclusive, clôture, reconduction (copie de structure montants à zéro), répertoire de
  tâches/lignes réutilisable.
- Gestion des **tâches** et **lignes budgétaires** (budgets initiaux, agrégats calculés).
- **Virements budgétaires** entre lignes (transferts + / −) avec motif et traçabilité.
- **Journal de programmation (JP-BC)** : plan annuel des prestations par BC
  (période quadrimestre/pentamestre, priorité 1/2, nature APPRO / Travaux / Prestations
  intellectuelles), génération d'une DA pré-remplie depuis une prestation.
- **Demandes d'achat** : cycle de vie complet, pièces jointes, contrôle du solde.
- **Offres prestataires** : sollicitation, saisie, retenue/refus.
- **Bons de commande** : format réel PAD (objet, articles, CAPRI, conditions de paiement,
  RIB, délai en semaines), transitions d'état, prolongation d'échéance motivée,
  édition PDF officielle, imputations budgétaires.
- **Consommations directes** : module dédié (saisie avec CAPRI et pièce jointe,
  édition réservée à l'administrateur, annulation motivée avec restitution du budget).
- **Bilans** : indicateurs globaux, par tâche et par ligne, période annuelle /
  trimestrielle / mensuelle / personnalisée, exports CSV et PDF.
- **Prestataires** : référentiel fournisseurs.
- **Journal d'activité** : historique immuable signé (chaîne de hachage SHA-256).
- **Notifications** internes par rôle (badge temps réel).
- **Recherche globale** transverse.
- **Administration** : comptes et rôles, réinitialisation de mot de passe,
  activation/désactivation, paramètres, export RGPD.
- **Reprise des données réelles 2026** : commande de chargement embarquant les données
  officielles (suivi détaillé des tâches + journal JP-BC).

### 4.2 Exclu (hors périmètre actuel)

- Multi-directions (l'outil est mono-DRH ; le rôle « DAG » a été retiré).
- Interfaçage temps réel avec les SI comptables/financiers du PAD (la reprise se fait
  par import des états officiels).
- Signature électronique des documents.
- Application mobile native (l'interface web est responsive).
- Gestion de la paie ou des marchés publics au-delà du bon de commande.

---

## 5. Acteurs et rôles

| Rôle | Code | Droits principaux |
|---|---|---|
| **Administrateur** | `admin` | Tous droits : édition globale (y compris codes/libellés des lignes, prestations du journal, consommations), annulations (virements, consommations), gestion des utilisateurs, paramètres |
| **Directeur DRH** | `directeur_drh` | Validation des DA, virements, consultation globale |
| **Chef de service** | `chef_service` | Création et suivi des DA |
| **Assistante DRH** | `assistante_drh` | Saisie des DA, consommations, tâches |
| **Lecteur** | `lecteur` | Consultation seule (auditeur, contrôle) |

Principes : tout utilisateur est authentifié ; `admin` hérite de tous les droits ;
les actions d'écriture sont contrôlées par décorateur de rôle côté serveur
(le masquage des boutons côté interface n'est qu'un confort).

---

## 6. Exigences fonctionnelles

> Notation : **EF-x.y** = exigence fonctionnelle ; toutes les exigences listées sont
> **implémentées** dans l'état actuel.

### 6.1 Authentification et comptes

- **EF-1.1** Connexion par identifiant/mot de passe ; déconnexion.
- **EF-1.2** Verrouillage anti-force brute : 5 échecs → blocage 1 h (couple IP + compte), réinitialisé en cas de succès.
- **EF-1.3** Changement de mot de passe forcé à la première connexion ou après réinitialisation par l'admin (middleware bloquant).
- **EF-1.4** Gestion des comptes par l'admin : création, modification, rôle, activation/désactivation, réinitialisation du mot de passe, suppression.

### 6.2 Exercices budgétaires

- **EF-2.1** Création d'un exercice via un assistant en 4 étapes (année/dates → tâches → lignes/budgets → récapitulatif), avec préservation des saisies entre étapes.
- **EF-2.2** Activation exclusive : activer un exercice désactive automatiquement tous les autres (règle R7), protégée contre les accès concurrents.
- **EF-2.3** Clôture définitive : l'exercice passe en lecture seule (toute écriture est refusée).
- **EF-2.4** Reconduction : création de l'exercice N+1 par copie des tâches/lignes actives, montants à zéro.
- **EF-2.5** Répertoire réutilisable de tâches/lignes pour accélérer la création d'exercices.
- **EF-2.6** Sélecteur d'exercice courant (consultation des exercices passés).

### 6.3 Tâches et lignes budgétaires

- **EF-3.1** CRUD des tâches (numéro unique par exercice, titre) et de leurs lignes (code nature, libellé, budget initial ≥ 0).
- **EF-3.2** Agrégats calculés par ligne et par tâche : transferts + / −, budget ajusté, consommation (BC + directes), solde, taux de consommation.
- **EF-3.3** Seuils d'alerte visuels sur le taux : ≥ 70 % avertissement, ≥ 90 % danger ; notification au dépassement du seuil paramétré de l'exercice.
- **EF-3.4** L'admin peut modifier le code et le libellé d'une ligne ; tolérance de saisie des montants au format français (espaces, virgule décimale).

### 6.4 Virements budgétaires (transferts)

- **EF-4.1** Virement d'un montant d'une ligne source vers une ligne destination (lignes distinctes), motif obligatoire.
- **EF-4.2** Contrôle du solde disponible de la ligne source avant exécution.
- **EF-4.3** Annulation par l'admin : génération d'un virement inverse motivé (traçabilité préservée), sous réserve du solde de la ligne destination.

### 6.5 Journal de programmation (JP-BC)

- **EF-5.1** Registre annuel des prestations programmées au format officiel : n° d'ordre, tâche, code nature, objet, nature (APPRO / Travaux / Prestations intellectuelles), montant HT, budget prévisionnel, période d'engagement (quadrimestre mars–juin / pentamestre juil.–nov.), priorité (1/2), statut (programmée, en cours, exécutée, annulée).
- **EF-5.2** Indicateurs : totaux, répartition par statut, budget prévisionnel, montant HT planifié ; filtres période/priorité/statut.
- **EF-5.3** Génération d'une **DA pré-remplie** depuis une prestation disponible (liaison conservée, prestation passée « en cours »).
- **EF-5.4** CRUD des prestations réservé à l'admin, via panneau latéral (offcanvas) ; lecture seule pour les autres rôles.

### 6.6 Demandes d'achat (DA)

- **EF-6.1** Cycle de vie : **Créée → Transmise DAG → Validée → BC créé**, avec **Annulée** possible depuis Créée/Transmise (motif obligatoire) ; transitions contrôlées par machine à états.
- **EF-6.2** Référence auto-générée au format PAD `DAC{AAMM}DLA{NNNNN}` (séquence mensuelle atomique).
- **EF-6.3** Saisie : ligne budgétaire d'imputation, objet, montant estimé, nature de prestation, période d'engagement, priorité.
- **EF-6.4** Contrôle du solde disponible de la ligne à la création et à la modification.
- **EF-6.5** Validation conditionnée à la présence d'une pièce jointe probante (facture proforma ou DA signée).
- **EF-6.6** Pièces jointes multiples typées avec titre personnalisé ; notification des valideurs à la création.

### 6.7 Offres et prestataires

- **EF-7.1** Référentiel prestataires (code auto `PREST-NNN`, coordonnées) avec CRUD.
- **EF-7.2** Sollicitation d'offres sur une DA, saisie des montants, retenue d'une offre (les autres étant refusées), refus motivé.

### 6.8 Bons de commande (BC)

- **EF-8.1** Numéro auto au format PAD `STD{AAMM}DLA{NNNNN}` (séquence mensuelle atomique, resynchronisation automatique après import).
- **EF-8.2** Contenu conforme au document officiel : prestataire, objet, articles (référence, désignation, unité, quantité, prix unitaire HT), TVA 19,25 %, totaux HT/TVA/TTC, conditions de paiement, RIB, délai d'exécution en semaines, date de notification, échéance calculée.
- **EF-8.3** Avis **CAPRI** (n° + date) obligatoire à la création/modification (règle R11) ; badge « à régulariser » sur l'existant incomplet.
- **EF-8.4** Transitions d'état : créé → notifié → en cours → exécuté ; annulation motivée ; un BC exécuté est immuable (règle R3).
- **EF-8.5** Imputations budgétaires du BC sur les lignes (consommation TTC).
- **EF-8.6** Prolongation d'échéance motivée avec historique.
- **EF-8.7** Édition PDF du BC au gabarit officiel PAD (bilingue, charte graphique).

### 6.9 Consommations directes

- **EF-9.1** Module dédié : registre filtrable (statut, tâche), indicateurs (actives, annulées, montant, CAPRI à régulariser).
- **EF-9.2** Saisie : ligne budgétaire, montant, motif typé (achat direct, assistance sociale, urgence, remboursement, correction, autre), description, date, **CAPRI obligatoire**, pièce jointe facultative (validée : taille ≤ 10 Mo, extension et contenu).
- **EF-9.3** Contrôle du solde disponible à la création **et** à la modification (réintégration de l'ancien montant).
- **EF-9.4** Édition réservée à l'**admin** via offcanvas ; lecture seule pour les autres rôles ; une consommation annulée n'est plus modifiable.
- **EF-9.5** Annulation par l'admin avec motif (≥ 5 caractères) : conservation en base (soft-delete), restitution du budget, traçabilité (auteur, date, motif).

### 6.10 Bilans et restitution

- **EF-10.1** Tableau de bord : budget global, total engagé (BC **+** consommations directes), solde, taux, top 5 des tâches, répartition des BC par statut, BC en retard / à échéance ≤ 7 jours, alertes.
- **EF-10.2** Bilans périodiques : année complète, trimestre, mois ou période personnalisée ; indicateurs globaux, top 10 tâches, détail des engagements par BC.
- **EF-10.3** Exports : CSV (suivi détaillé par tâche/ligne) et PDF (état périodique au gabarit officiel).
- **EF-10.4** Détail des engagements (journal des imputations par BC).

### 6.11 Traçabilité, notifications, transverse

- **EF-11.1** Journal d'activité immuable : chaque action sensible est consignée (type, description, entité, auteur, horodatage) et chaînée par hachage SHA-256 (`prev_hash`/`hash_chain`) ; commandes de vérification et de reconstruction de la chaîne.
- **EF-11.2** Notifications internes ciblées par rôle (ex. DA à valider) avec badge non-lu et marquage groupé.
- **EF-11.3** Recherche globale (tâches, lignes, DA, BC, prestataires).
- **EF-11.4** Export RGPD des données personnelles d'un utilisateur.
- **EF-11.5** Reprise des données réelles : commande `seed_real_data` (options `--reset`, `--flush`) chargeant l'exercice 2026 officiel — 58 tâches, 130 lignes, transferts reconstitués en virements, 40 consommations, 36 prestations du journal — avec comptes de démonstration.

---

## 7. Règles de gestion

| Réf. | Règle | Application |
|---|---|---|
| **R1** | Une imputation (DA, BC, consommation, virement) ne peut excéder le **solde disponible** de la ligne | Contrôle bloquant à la saisie et à la modification (service centralisé) |
| **R3** | Un BC **exécuté** est immuable | Transitions verrouillées par machine à états |
| **R7** | Un **seul exercice actif** à la fois | Activation exclusive atomique (verrou en base) |
| **R10** | Aucune écriture sur un exercice **clôturé/verrouillé** | Contrôle centralisé dans toutes les vues d'écriture |
| **R11** | Tout engagement (BC, consommation directe) requiert un **avis CAPRI** préalable (n° + date) | Champs obligatoires ; badge « à régulariser » sur l'historique antérieur |
| RG-TVA | TVA au taux camerounais de **19,25 %** ; total TTC = HT × 1,1925 | Calcul automatique sur BC et lignes d'articles |
| RG-Seuils | Alerte à **70 %** (avertissement) et **90 %** (danger) du taux de consommation | Code couleur + notifications |
| RG-Num | Numérotation officielle `DAC{AAMM}DLA{NNNNN}` (DA) et `STD{AAMM}DLA{NNNNN}` (BC), séquences mensuelles **atomiques** | Générateur avec verrou (`select_for_update`) et resynchronisation |
| RG-Annul | Toute annulation (DA, BC, virement, consommation) exige un **motif** et reste tracée | Soft-delete / contre-écriture + journal |
| RG-PJ | Validation d'une DA conditionnée à une pièce probante (proforma ou DA signée) ; fichiers contrôlés (10 Mo max, types autorisés, signature binaire) | Contrôle serveur |

---

## 8. Exigences non fonctionnelles

### 8.1 Sécurité

- **ENF-1.1** Authentification obligatoire sur toutes les pages ; contrôle des rôles côté serveur sur chaque action d'écriture.
- **ENF-1.2** Anti-force brute (django-axes) : 5 tentatives, blocage 1 h par IP+compte.
- **ENF-1.3** Changement de mot de passe forcé (première connexion / réinitialisation).
- **ENF-1.4** Protections Django : CSRF, échappement XSS, ORM exclusif (aucune requête SQL brute).
- **ENF-1.5** Profil production : `DEBUG=False`, clé secrète par variable d'environnement (démarrage refusé sinon), HTTPS forcé, HSTS 1 an, cookies `Secure`, `nosniff`, referrer-policy stricte, URL d'admin configurable.
- **ENF-1.6** Téléversements contrôlés (taille, extension, signature de contenu).
- **ENF-1.7** Journal d'audit infalsifiable (chaîne de hachage vérifiable).

### 8.2 Performance et scalabilité

- **ENF-2.1** Agrégats budgétaires calculés en base par sous-requêtes corrélées (exactitude garantie même avec relations multiples — pas de produit cartésien).
- **ENF-2.2** Listes paginées (25 éléments ; journal 50).
- **ENF-2.3** Index de base de données sur les axes de filtrage (statuts, exercice, dates, entités du journal) — 9 index dédiés en plus des clés.
- **ENF-2.4** Absence de requêtes N+1 sur les écrans de liste et les exports (préchargements et requêtes groupées).

### 8.3 Ergonomie

- **ENF-3.1** Interface en **français**, responsive (Bootstrap 5), charte PAD (vert `#1A5632`, bleu marine `#1B3A5C`), logo officiel.
- **ENF-3.2** Navigation latérale par module ; recherche globale ; sélecteur d'exercice.
- **ENF-3.3** Consultation/édition contextuelle par panneaux latéraux (offcanvas) et fenêtres modales ; messages de confirmation/erreur explicites en français.
- **ENF-3.4** Formats locaux : montants FCFA avec séparateur de milliers, saisie tolérante (virgule décimale), dates jj/mm/aaaa.

### 8.4 Maintenabilité et qualité

- **ENF-4.1** Architecture en couches : modèles (règles + agrégats), **couche services** (logique métier transactionnelle), vues, gabarits.
- **ENF-4.2** Suite de **65 tests automatisés** (pytest) couvrant services, règles de gestion, modules récents et reprise de données ; exécution sur base isolée.
- **ENF-4.3** Audit technique versionné (`docs/audit_technique.md`) : cartographie, dette, refactorings appliqués et backlog.
- **ENF-4.4** Documentation : README, guide d'installation (Markdown + Word), diagrammes de classes (draw.io, JSON, Markdown).
- **ENF-4.5** Gestion de configuration par environnement (`.env`, profils dev/prod/test).

### 8.5 Compatibilité et exploitation

- **ENF-5.1** Serveur : Windows ou Linux ; Python ≥ 3.12 ; MySQL 8+ / MariaDB 10.6+ (UTF-8 mb4).
- **ENF-5.2** Clients : navigateurs récents (Chrome, Edge, Firefox).
- **ENF-5.3** Déploiement local intranet ; commandes d'administration (seed, audit d'intégrité, reconstruction de chaîne, réinitialisation de mots de passe).

---

## 9. Architecture technique

### 9.1 Pile logicielle

| Couche | Technologie |
|---|---|
| Langage | Python 3.14 |
| Framework | Django 6.0 (MVT + couche services) |
| Base de données | MySQL/MariaDB (utf8mb4) |
| Interface | Bootstrap 5, Bootstrap Icons, Chart.js |
| PDF | ReportLab |
| Sécurité | django-axes, middleware dédiés |
| Tests | pytest, pytest-django, factory_boy |

### 9.2 Flux applicatif

```
[Navigateur] → urls.py → views (contrôle rôle/exercice)
            → services (BonCommande, DemandeAchat, Virement, Budget,
                        Sequence, Notification, Tache, PDF)
            → modèles + agrégats SQL → MySQL
            → gabarits HTML (Bootstrap) → [Réponse]
```

### 9.3 Modèle de données (principales entités)

`ExerciceBudgetaire` 1—n `Tache` 1—n `LigneBudgetaire` ;
`VirementBudgetaire` (ligne source/destination) ;
`PrestationProgrammee` n—1 `LigneBudgetaire`, 1—1 `DemandeAchat` ;
`DemandeAchat` 1—n `Offre` (n—1 `Prestataire`) ; `BonCommande` 1—n `LigneBC`,
1—n `ImputationBC` (n—1 `LigneBudgetaire`), 1—n `ProlongationBC` ;
`ConsommationDirecte` n—1 `LigneBudgetaire` ;
`PieceJointe` (rattachement polymorphe) ; `JournalActivite` (chaîne SHA-256) ;
`Notification`, `Alerte`, `Sequence`, `Utilisateur` (rôles).

*(Diagramme complet : `docs/budgetpad_class_diagram.drawio`.)*

---

## 10. Données reprises (exercice 2026)

Reprise fidèle des états officiels DRH au 08/06/2026, embarquée dans l'application :

| Donnée | Valeur | Source |
|---|---|---|
| Tâches / lignes budgétaires | **58 / 130** | PDF « Suivi détaillé des tâches » |
| Budget global ajusté | **6 727 266 993 FCFA** | idem |
| Transferts reconstitués | 15 virements (équilibrés) | idem |
| Consommations | 40 écritures — **1 692 877 445 FCFA** | idem |
| Prestations au journal | **36** — 140 952 000 FCFA HT | Excel « JP-BC DRH 2026 » |
| Fidélité | **0 écart** ligne à ligne (solde recalculé = solde officiel) | tests automatisés |

---

## 11. Livrables

1. **Application web** BudgetPAD (code source versionné, branche principale + PR documentées).
2. **Base de données** initialisée avec les données réelles 2026 (commande `seed_real_data`).
3. **Documentation** : README, guide d'installation (`.md` + `.docx`), cahier des charges (présent document), audit technique, diagrammes de classes (draw.io / JSON / Markdown).
4. **Suite de tests** automatisés (65 tests) et commandes d'audit d'intégrité.
5. **Comptes de démonstration** (5 rôles, mot de passe initial commun).

---

## 12. Recette — critères d'acceptation

| Critère | Méthode de vérification | État |
|---|---|---|
| Les 65 tests automatisés passent | `pytest` | ✅ |
| Configuration valide | `manage.py check` → 0 problème | ✅ |
| Fidélité des données 2026 (budget ajusté, consommation, solde par tâche) | Comparaison automatisée app ↔ PDF officiel : 58/58 conformes | ✅ |
| Journal JP-BC conforme | Total HT 140 952 000 ; répartition 21/4/11/0 | ✅ |
| Numérotation PAD sans doublon sous concurrence | Tests de séquence atomique | ✅ |
| Blocages métier (solde, CAPRI, exercice clôturé, rôles) | Tests + parcours manuels | ✅ |
| PDF BC et bilans conformes aux gabarits | Revue visuelle avec l'encadrement | ✅ |
| Installation reproductible sur un poste tiers | Guide d'installation (cas dossier transféré et cas Git) | ✅ |

---

## 13. Évolutions prévues (backlog)

- Découpage du module `views.py` (~3 600 lignes) en sous-modules par domaine.
- Centralisation des statuts en énumérations (`TextChoices`).
- Unification des résolveurs de période (dashboard/bilans) et injection de l'exercice
  courant par context processor.
- Import direct des fichiers officiels (Excel JP-BC, états PDF) depuis l'interface.
- Tableaux de bord complémentaires (projection de consommation, comparaison N/N-1).
- Déploiement intranet PAD (serveur dédié, sauvegardes planifiées).

---

## 14. Glossaire

| Terme | Définition |
|---|---|
| **BC** | Bon de commande |
| **DA** | Demande d'achat |
| **CAPRI** | Avis préalable de la Direction du Contrôle de Gestion autorisant un engagement |
| **DAG** | Direction de l'Administration Générale (destinataire des DA transmises) |
| **DCG** | Direction du Contrôle de Gestion |
| **JP-BC** | Journal de programmation par bons de commande (plan annuel des prestations) |
| **Code nature** | Code comptable d'une ligne budgétaire (ex. 6047210) |
| **Tâche budgétaire** | Activité budgétée regroupant des lignes (ex. 3213003 — Gestion santé) |
| **Budget ajusté** | Budget initial + transferts entrants − transferts sortants |
| **Consommation** | Imputations de BC (TTC) + consommations directes non annulées |
| **Solde** | Budget ajusté − consommation |
| **Quadrimestre / Pentamestre** | Périodes d'engagement du JP-BC (mars–juin / juillet–novembre) |
| **FCFA** | Franc CFA (XAF) |
