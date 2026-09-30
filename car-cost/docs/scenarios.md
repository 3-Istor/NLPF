# Scénarios — fonctionnement et aide à la décision

Ce document est le point d'entrée unique pour comprendre ce qui a été réalisé autour des
scénarios, des paramètres, du calcul, de la comparaison et de la recommandation de sourcing.
Il décrit le comportement final du produit, les fichiers concernés, les vérifications effectuées
et la prochaine tranche consacrée au CO₂.

État vérifié le **28 septembre 2026**. Tous les prix, masses, facteurs carbone et données de
nomenclature du projet sont **synthétiques** : aucun chiffre ne provient d'un constructeur.

## 1. Ce qui est opérationnel

Les quatre fonctionnalités d'aide à la décision prévues pour les scénarios sont en place :

- **NLPF-42 — gérer les scénarios** : créer, lister, relire, dupliquer et supprimer un scénario ;
- **NLPF-43 — paramétrer puis calculer** : modifier une pièce ou une occurrence précise, supprimer
  un paramètre et recalculer le coût ;
- **NLPF-44 — comparer deux scénarios** : calculer A et B avec les mêmes références puis expliquer
  le delta de coût `B - A` ;
- **NLPF-45 — recommander un sourcing** : chercher le couple fournisseur/usine le moins cher sous
  les contraintes demandées et créer une variante indépendante.

La recette Swagger effectuée confirme le parcours complet : scénario de base, paramètres,
suppression, calcul, comparaison et recommandation. Le seul champ fonctionnellement incomplet dans
ce parcours est `co2_delta_kg`, qui vaut actuellement `null` parce que le moteur ne calcule pas
encore l'empreinte carbone.

## 2. Les notions à connaître

### BOM et DAG

La **BOM** (*Bill of Materials*) est la nomenclature : la liste des pièces et les relations
parent-enfant qui composent le véhicule.

Cette nomenclature est un **DAG** (*Directed Acyclic Graph*, ou graphe orienté acyclique) :

- les flèches vont d'un ensemble vers ses composants ;
- une pièce peut avoir plusieurs parents et être utilisée à plusieurs endroits ;
- aucun chemin ne peut revenir à son point de départ.

Une vis partagée par le moteur et la caisse n'est donc stockée qu'une fois, mais possède plusieurs
**occurrences**, c'est-à-dire plusieurs chemins depuis la racine. Sa **quantité cumulée** est la
somme des produits de quantités rencontrées sur tous ces chemins. C'est pour cette raison que le
moteur ne peut pas traiter la BOM comme un simple arbre.

### Scénario et paramètre

Un **scénario** ne contient pas une copie des 474 pièces. Il contient :

- une version de BOM ;
- une devise d'affichage ;
- un taux horaire ;
- les règles actives ;
- seulement les **écarts** par rapport aux données de référence.

Un scénario avec un seul paramètre utilise donc bien toute la nomenclature. Ce paramètre est
simplement la seule valeur remplacée. À l'inverse, la recommandation peut produire beaucoup de
paramètres parce qu'elle enregistre un nouveau choix de sourcing pour chaque pièce acceptée.

Chaque paramètre possède un `parameter_id` de forme `prm-…`. Cet identifiant est renvoyé par le
`PUT`, mais aussi par `GET /scenarios` et `GET /scenarios/{id}` afin qu'un paramètre reste facile à
retrouver et à supprimer.

### Portée `part` et portée `path`

- `scope: "part"` applique le réglage à **toutes les occurrences** de la référence ciblée ;
- `scope: "path"` l'applique à **une seule occurrence**, identifiée par son chemin complet depuis
  la racine.

Si les deux portées existent sur la même pièce, le paramètre de chemin, plus précis, l'emporte pour
cette occurrence. Le paramètre de pièce continue de s'appliquer aux autres occurrences.

### Snapshot de prix

Un **snapshot** est une photographie datée et immuable des prix. Tous les calculs d'une comparaison
utilisent le même snapshot pour éviter qu'un changement de prix externe soit confondu avec l'effet
des paramètres du scénario. Un prix manquant ne devient jamais zéro : le calcul est déclaré
`INCOMPLETE` et nomme les pièces concernées.

## 3. Parcours d'une requête dans le code

```text
Swagger / interface
        │
        ▼
Routes FastAPI (validation HTTP et format JSON)
        │
        ▼
Services d'application (orchestration du cas d'usage)
        │
        ├──► Domaine pur (règles et calcul sur le DAG)
        │
        ▼
Ports de dépôt
        │
        ▼
PostgreSQL / API de prix
```

Cette séparation permet de tester le moteur sans FastAPI, PostgreSQL ni réseau. Les routes ne
portent pas les règles de calcul et les requêtes SQL restent limitées à la persistance.

## 4. Endpoints disponibles

Toutes les routes ci-dessous sont préfixées par `/api/v1`.

| Méthode et route | Rôle |
|---|---|
| `POST /scenarios` | Créer et valider un scénario nommé. |
| `GET /scenarios` | Lister les scénarios et retrouver leurs identifiants et paramètres. |
| `GET /scenarios/{scenario_id}` | Relire un scénario complet et l'état de son dernier calcul. |
| `POST /scenarios/{scenario_id}/duplicate` | Créer une copie indépendante sans copier les calculs. |
| `DELETE /scenarios/{scenario_id}` | Supprimer le scénario, ses paramètres et ses calculs. |
| `PUT /scenarios/{scenario_id}/parameters/{target}` | Ajouter ou remplacer le paramètre d'une pièce ou d'un chemin. |
| `DELETE /scenarios/{scenario_id}/parameters/{parameter_id}` | Supprimer un paramètre précis. |
| `POST /calculations` | Calculer un scénario avec un snapshot donné ou le plus récent. |
| `GET /calculations/{calculation_id}` | Relire un calcul enregistré. |
| `GET /calculations/{calculation_id}/aggregated` | Obtenir une ligne agrégée par référence de pièce. |
| `POST /scenarios/compare` | Calculer puis comparer les scénarios A et B. |
| `POST /scenarios/{scenario_id}/recommend-sourcing` | Créer une variante de sourcing optimisée. |
| `GET /price-snapshots` | Lister les snapshots, leur âge et leur état. |
| `GET /price-snapshots/{snapshot_id}/quarantine` | Expliquer les prix écartés ou remplacés. |

La suppression d'un scénario conserve la BOM et les snapshots, car ils peuvent servir à d'autres
scénarios. PostgreSQL supprime en cascade les paramètres, calculs et résultats qui dépendent
uniquement du scénario supprimé.

## 5. Comment le coût est calculé

Le moteur parcourt le DAG dans un ordre topologique. Il calcule chaque pièce une seule fois pour la
vue agrégée, puis propage correctement les quantités sur tous les chemins.

Pour une pièce achetée, le prix résolu suit ce principe :

```text
prix unitaire = prix du snapshot × multiplicateur fournisseur × coefficient usine
```

Un `price_override` justifié remplace ce prix. Pour une pièce fabriquée, le coût propre provient de
la main-d'œuvre et le coût complet comprend aussi ses enfants. Les deux valeurs importantes sont :

- `own_contribution` : contribution propre de la ligne, qui participe à la somme du total ;
- `rolled_up_contribution` : poids complet de l'occurrence, enfants inclus, utile pour expliquer la
  structure mais qui ne doit pas être additionné entre niveaux.

L'arrondi se fait uniquement à l'affichage. Les montants circulent sous forme de chaînes décimales
afin de conserver le résultat exact et de rendre une addition accidentelle dans le navigateur
immédiatement visible.

Après la modification d'un paramètre, `calculation_state` devient `PARAMETERS_CHANGED`. Un nouveau
calcul enregistre son scénario, sa BOM, son snapshot, son horodatage, son statut et une empreinte
des entrées. Ces références rendent le résultat explicable et rejouable.

## 6. Comparaison de scénarios

`POST /scenarios/compare` exécute les deux scénarios avec le même snapshot. Les scénarios doivent
partager la même version de BOM et la même devise d'affichage.

La réponse contient :

- `total_a` et `total_b` ;
- `cost_delta`, toujours calculé comme **B moins A** ;
- jusqu'à dix `top_differences`, classées par importance absolue ;
- `co2_delta_kg`, actuellement à `null`.

Si les totaux sont identiques et `top_differences` est vide, les deux scénarios produisent le même
coût avec le snapshot choisi. Cela peut arriver si les paramètres sont identiques, si la variante
n'applique aucune recommandation, ou si un changement n'a aucun effet sur le prix résolu.

La comparaison refuse un calcul incomplet. Cette règle empêche de présenter comme une économie la
disparition artificielle d'un coût dont le prix est inconnu.

## 7. Recommandation de sourcing

La recommandation examine chaque pièce achetée qui ne possède pas de prix forcé. Pour chaque pièce,
elle :

1. énumère les couples fournisseur/usine connus ;
2. écarte les provenances interdites et les délais supérieurs à la limite ;
3. calcule le prix unitaire de chaque option avec le snapshot ;
4. retient l'option la moins chère ;
5. explique l'option actuelle, l'option proposée, la quantité affectée et l'économie estimée ;
6. crée un **nouveau scénario**, sans modifier l'original.

`accepted_part_refs` contrôle les recommandations réellement appliquées :

- champ omis ou `null` : toutes les recommandations sont acceptées ;
- liste vide `[]` : une copie indépendante est créée sans changement ;
- liste de références : seules ces recommandations sont appliquées.

L'algorithme optimise chaque pièce indépendamment. Il ne cherche pas une combinaison globale avec
des contraintes couplées entre plusieurs pièces. Une telle optimisation est un problème métier
distinct.

## 8. Fichiers créés ou modifiés pour cette fonctionnalité

### Domaine

- [`backend/src/carcost/domain/scenario.py`](../backend/src/carcost/domain/scenario.py) définit le
  scénario, ses paramètres et leur portée explicite.
- [`backend/src/carcost/domain/engine.py`](../backend/src/carcost/domain/engine.py) applique les
  paramètres par pièce ou par chemin pendant le calcul du DAG.

### Application

- [`backend/src/carcost/application/manage_scenarios.py`](../backend/src/carcost/application/manage_scenarios.py)
  orchestre la création, la duplication et la validation des paramètres.
- [`backend/src/carcost/application/compare_scenarios.py`](../backend/src/carcost/application/compare_scenarios.py)
  compare deux résultats complets et produit les principaux écarts.
- [`backend/src/carcost/application/recommend_sourcing.py`](../backend/src/carcost/application/recommend_sourcing.py)
  évalue les options autorisées et construit les recommandations déterministes.
- [`backend/src/carcost/application/price_resolution.py`](../backend/src/carcost/application/price_resolution.py)
  résout le prix effectif après application du sourcing et des surcharges.
- [`backend/src/carcost/application/run_calculation.py`](../backend/src/carcost/application/run_calculation.py)
  coordonne le chargement des entrées, le moteur et la sauvegarde du calcul.
- [`backend/src/carcost/application/scenario.py`](../backend/src/carcost/application/scenario.py)
  choisit le paramètre applicable et gère la priorité du chemin sur la pièce.
- [`backend/src/carcost/application/tree_view.py`](../backend/src/carcost/application/tree_view.py)
  prépare les informations de portée et d'occurrences destinées à l'API.
- [`backend/src/carcost/application/ports.py`](../backend/src/carcost/application/ports.py) décrit les
  opérations de persistance attendues par l'application, sans dépendre de PostgreSQL.

### Infrastructure et API

- [`backend/src/carcost/infrastructure/api/calculation_routes.py`](../backend/src/carcost/infrastructure/api/calculation_routes.py)
  expose les routes de scénario, paramètre, calcul, comparaison et recommandation dans Swagger.
- [`backend/src/carcost/infrastructure/api/snapshot_routes.py`](../backend/src/carcost/infrastructure/api/snapshot_routes.py)
  expose la liste des snapshots et le journal de quarantaine.
- [`backend/src/carcost/infrastructure/postgres_repositories.py`](../backend/src/carcost/infrastructure/postgres_repositories.py)
  sauvegarde et relit les scénarios, leurs `parameter_id` et les calculs ; il porte aussi la
  suppression d'un scénario.
- [`backend/tests/fakes.py`](../backend/tests/fakes.py) fournit les dépôts en mémoire utilisés par
  les tests rapides de l'application.

### Tests

- [`backend/tests/application/test_manage_scenarios.py`](../backend/tests/application/test_manage_scenarios.py)
  vérifie les règles de création, duplication et validation.
- [`backend/tests/infrastructure/test_scenario_routes.py`](../backend/tests/infrastructure/test_scenario_routes.py)
  vérifie les contrats HTTP, les réponses Swagger et les erreurs attendues.
- [`backend/tests/integration/test_postgres_scenarios.py`](../backend/tests/integration/test_postgres_scenarios.py)
  vérifie l'aller-retour réel en base, les identifiants et les suppressions en cascade.
- [`backend/tests/scenarios/test_api_workflow.py`](../backend/tests/scenarios/test_api_workflow.py)
  couvre le parcours API de bout en bout.
- [`backend/tests/scenarios/test_parameterized_calculation.py`](../backend/tests/scenarios/test_parameterized_calculation.py)
  vérifie l'effet des paramètres de pièce et de chemin sur le calcul.
- [`backend/tests/scenarios/test_comparison.py`](../backend/tests/scenarios/test_comparison.py)
  vérifie le delta `B - A`, les invariants et le classement des différences.
- [`backend/tests/scenarios/test_recommendation.py`](../backend/tests/scenarios/test_recommendation.py)
  vérifie les contraintes, l'acceptation partielle et l'indépendance du scénario créé.
- [`backend/tests/infrastructure/test_snapshot_routes.py`](../backend/tests/infrastructure/test_snapshot_routes.py)
  et [`backend/tests/integration/test_postgres_price_snapshots.py`](../backend/tests/integration/test_postgres_price_snapshots.py)
  vérifient la lecture et la persistance des snapshots.

### Documentation

- [`docs/api.md`](api.md) contient le contrat détaillé de chaque endpoint.
- [`docs/adr/0002-portee-des-parametres-piece-ou-chemin.md`](adr/0002-portee-des-parametres-piece-ou-chemin.md) explique la décision de
  supporter les portées pièce et chemin.
- [`docs/perimetre.md`](perimetre.md) situe ces fonctionnalités dans les tranches du projet.
- [`../README.md`](../../README.md) décrit l'installation et le lancement général du projet.

Aucune migration de schéma n'a été ajoutée pour cette tranche : les tables et les clés étrangères
nécessaires existaient déjà. Le fichier `output/pdf/etat-scenarios-nlpf.pdf` est un document de
revue généré, pas du code exécuté par l'application.

## 9. Vérifications réalisées

Les contrôles suivants ont réussi sur PostgreSQL et le jeu de données complet :

- **287 tests backend** ;
- **15 tests frontend** ;
- vérification TypeScript avec `tsc --noEmit` ;
- contrôle du générateur déterministe avec `python -m tools.bom_generator --check` ;
- contrôle des espaces et fins de ligne avec `git diff --check`.

Le jeu de données de validation contient **474 pièces**, **689 relations**, **302 pièces achetées**,
**172 pièces fabriquées**, **65 pièces partagées**, **749 chemins** et une profondeur maximale de
**5**.

## 10. Lancer Swagger sous Windows

Depuis `C:\Users\rapha\NLPF\car-cost`, utiliser trois terminaux PowerShell.

Terminal 1 — PostgreSQL et chargement idempotent des données :

```powershell
$env:POSTGRES_PORT = '55432'
docker compose up -d
.\backend\.venv\Scripts\python.exe -m carcost.infrastructure seeds |
  docker compose exec -T db psql -U 3istor -d 3istor -v ON_ERROR_STOP=1 -q
```

Terminal 2 — simulateur de prix :

```powershell
.\backend\.venv\Scripts\python.exe price-api/mock_price_api.py --port 8099
```

Terminal 1 — créer un snapshot :

```powershell
$env:CARCOST_DSN = 'postgresql://3istor:3istor@127.0.0.1:55432/3istor'
.\backend\.venv\Scripts\python.exe -m carcost.infrastructure.snapshot_cli
```

Terminal 3 — API. Le port `8001` est utilisé ici parce que le port `8000` était déjà occupé sur la
machine de recette :

```powershell
$env:CARCOST_DSN = 'postgresql://3istor:3istor@127.0.0.1:55432/3istor'
.\backend\.venv\Scripts\python.exe -m uvicorn carcost.infrastructure.api.main:app `
  --host 127.0.0.1 --port 8001
```

Swagger est alors disponible sur <http://127.0.0.1:8001/docs>. L'erreur Windows `10048` signifie
qu'un autre processus écoute déjà sur le port demandé ; il faut réutiliser ce service, arrêter son
processus, ou choisir un autre port libre.

L'ordre de test conseillé dans Swagger est :

1. `GET /price-snapshots` ;
2. `POST /scenarios` ;
3. `GET /scenarios/{id}` ;
4. `PUT /scenarios/{id}/parameters/{target}` ;
5. `POST /calculations` ;
6. `POST /scenarios/{id}/duplicate` puis modification de la copie ;
7. `POST /scenarios/compare` ;
8. `POST /scenarios/{id}/recommend-sourcing` ;
9. suppression d'un paramètre avec son `parameter_id` ;
10. suppression des scénarios de test.

Les schémas de requête, les champs obligatoires et les exemples de valeurs sont directement
visibles dans Swagger avec le bouton **Try it out** de chaque endpoint.

## 11. Prochaine tranche : calculer le CO₂

Le CO₂ mérite une tranche dédiée. Il ne suffit pas de remplir `co2_delta_kg` dans la réponse : le
total doit être calculé, expliqué, persisté et comparé avec les mêmes garanties que le coût.

Le projet possède déjà une partie des données nécessaires : masse et facteur carbone des pièces,
ainsi que le CO₂ de transport associé au sourcing. Le périmètre métier est également posé :
**extraction jusqu'à la sortie d'usine, transport fournisseur inclus, usage et fin de vie exclus,
sans taux de rebut**.

La mise en œuvre devrait suivre cet ordre :

1. écrire un test de domaine sur un DAG en losange pour prouver que le carbone d'une pièce partagée
   utilise la bonne quantité cumulée ;
2. définir précisément les unités de chaque donnée et la formule du transport ;
3. calculer `own_co2` et `rolled_up_co2` avec le même parcours que le coût ;
4. ajouter `total_co2`, la décomposition par système et les principaux contributeurs carbone au
   résultat persisté ;
5. renseigner `co2_delta_kg` dans la comparaison lorsque A et B possèdent tous deux un total ;
6. faire apparaître le compromis coût/CO₂ dans la recommandation, avec une contrainte métier
   explicite plutôt qu'un seuil inventé ;
7. mettre à jour Swagger, la recette manuelle et l'interface ;
8. exécuter à nouveau toute la suite de tests et le contrôle du générateur.

Avant l'étape 6, il faudra décider la règle attendue : minimiser le coût sous un plafond de CO₂,
minimiser le CO₂ sous un plafond de coût, ou présenter plusieurs options sans choisir à la place de
l'utilisateur. Le cadrage exclut actuellement l'optimisation combinatoire globale ; changer cette
décision demanderait un ADR.

## 12. Critère de fin pour la partie actuelle

La partie scénarios et aide à la décision peut être considérée comme terminée lorsque :

- les tests automatisés restent verts ;
- le parcours décrit dans la recette Swagger fonctionne sur une base fraîche ;
- chaque paramètre est récupérable et supprimable par son `parameter_id` ;
- supprimer un scénario conserve la BOM et les snapshots ;
- une comparaison utilise le même snapshot des deux côtés ;
- une recommandation crée une variante indépendante et laisse l'original intact ;
- la limite actuelle sur le CO₂ reste clairement visible jusqu'à la livraison de sa tranche.
