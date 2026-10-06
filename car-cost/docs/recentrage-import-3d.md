# Recentrage sur une seule feature : l'import d'une carrosserie 3D

- **Date** : 06/10/2026, commit `75a8a1a`.
- **Nature** : audit, proposition de nettoyage et cadrage. **Aucun code n'a été modifié**, rien n'a
  été supprimé ni commité. Ce fichier est la seule écriture.
- **Vérifié** :
  - `python -m pytest backend --ignore=backend/tests/integration` : **570 passés** (sans cache ni
    `.pyc` écrits) ;
  - lecture intégrale du domaine, de `ports.py` et des routes ; graphe d'import du front ;
    sous-graphe `CAR-ASSY` du Multipla relu dans `seeds/` ;
  - les tests nommés au §3 ont été retrouvés par lecture de leur corps, pas par leur nom de fichier.
- **Non vérifié** :
  - les 48 tests d'intégration Postgres et la suite front n'ont pas été relancés ;
  - l'écran n'a pas été piloté.

La feature visée : un designer importe un modèle 3D de carrosserie avec les specs de ses pièces.
L'outil en calcule le prix, et ce prix change avec la carrosserie importée.

**Mise à jour du 06/10 (3ᵉ passe)** : la feature est élargie (un modèle 3D par véhicule, une vue
3D liée à l'arbre) et le métier est vérifié par des sources. Les décisions sont au §0, le
compte rendu au §7.

---

## 0. Ce qu'il faut retenir

**La feature.** Chaque véhicule a son modèle 3D de carrosserie. L'**ingénieur carrosserie**
importe une variante du modèle (capot en aluminium, aileron…). L'outil en mesure les pièces, en
déduit les masses, crée une variante du véhicule et la chiffre. L'**ingénieur coût**, les achats et
le projet la voient en 3D, pièce par pièce, liée à l'arbre, avec l'écart de coût matière sur le
véhicule.

**Périmètre : le Multipla d'abord.** Les Valhalla se verront plus tard, et le §5 dit ce qu'il faut
y changer.

1. **C'est un vrai métier.** Le chiffrage à partir de la CAO existe en industrie : ingénieur coût,
   « design-to-cost », logiciels aPriori et Teamcenter Product Cost Management. La carrosserie
   seule est un découpage réaliste (§4.1, sources).
2. **Le moteur de coût ne change pas.** Une pièce de tôle du Multipla est déjà une pièce
   fabriquée avec une arête vers sa matière en kg (`CAR-HOOD-SHELL → MAT-STEEL-SHEET × 11,2 kg`).
   L'import ne fait que remplacer cette quantité par la masse mesurée.
3. **Les modèles de départ sont générés par script** : une maquette par véhicule, une forme par
   pièce. Les dimensions sont calculées pour que volume × densité redonne **exactement** la masse
   de la nomenclature. Rattacher la maquette ne change donc pas le prix.
4. **Le nettoyage se limite au code mort au sens strict** : six éléments, **aucun test
   supprimé** (§3).
5. **La démonstration est chiffrée et vérifiée avec le vrai moteur** (§4.8) :
   - aileron ABS : **+6,52 €** ;
   - capot de la maquette passé de l'acier à l'aluminium : **−1,33 € et −7,35 kg** ;
   - même fichier réimporté : **0,00 €**.

### Décisions du 06/10/2026

| # | Sujet | Décision |
|---|---|---|
| D1 | Vue 3D | **three.js, liée à l'arbre** : un clic sur une pièce sélectionne sa ligne, et inversement ; sur une variante, les pièces modifiées sont colorées. `<model-viewer>` est écarté, car il ne permet pas de lien avec le métier |
| D2 | Masse | **Calculée** : volume du **solide fermé** × densité de la matière |
| D3 | Densités | **Valeurs physiques usuelles**, ajoutées au jeu de données, marquées synthétiques, à relire |
| D4 | Modèles de départ | **Maquettes générées par script**, déterministes, à masse exacte |
| D5 | Ce que fait un import | Crée une **variante** du véhicule ouvert. Les pièces existantes du modèle sont remises à jour, les nouvelles ajoutées sous `CAR-ASSY`, les absentes restent inchangées |
| D6 | Périmètre | **Multipla seul** pour la réactivité au prix ; les Valhalla plus tard (§5) |
| D7 | Main-d'œuvre et CO₂ | **0 min** sur une pièce nouvelle ; **CO₂ masqué** sur une variante importée |
| D8 | Arrondi de la masse | **Pas de nouvelle règle** : l'échelle 10⁻⁶ de l'ADR-0011 s'applique. Le générateur garantit que sa maquette retombe exactement sur la masse de la nomenclature (§4.4) |
| D9 | Discussion | Devant l'écran, rien n'est enregistré. Commentaires par pièce : plus tard |
| D10 | Nettoyage | Code mort au sens strict seulement |
| D11 | Personas | **Ingénieur carrosserie** (importe), **ingénieur coût**, achats et projet (lisent). On ne parle plus de « designer » |

---

## 1. Audit de l'existant

Classes :

- **E** = essentiel (prix, arbre/BOM, import) ;
- **R** = réutilisable sous une forme simplifiée ;
- **I** = inutile pour cette feature.

Les chemins sont relatifs à `car-cost/`. `be/` désigne `backend/src/carcost/` et `fe/` désigne
`frontend/src/`.

### 1.1 Domaine (`be/domain/`, ≈ 930 lignes)

| Élément | Classe | Preuve | Tests |
|---|---|---|---|
| `bom.py` : `Part`, `Edge`, `Bom`, tri topologique | **E** | La carrosserie importée **est** un `Bom` ; `Part.mass_kg` existe déjà | `domain/test_bom_validation.py`, `domain/test_cost_engine.py`, `test_real_bom_control_values.py` |
| `bom_validation.py` : cycle, orphelin, achetée ⇔ feuille, fabriquée ⇒ main-d'œuvre | **E** | Doit refuser un import incohérent ; le code `MANUFACTURED_WITHOUT_LABOUR` pèse sur le cadrage (§4.3, question Q3) | `domain/test_bom_validation.py` (18) |
| `engine.py` : quantités cumulées, coût propre, cumul | **E** | `compute()` : c'est le prix | `domain/test_cost_engine.py` (30), `test_real_bom_control_values.py` (6) |
| `engine.py` : surcharges de chemin (`_path_costs`, `_path_adjustments`, `_average_path_overrides`, `_path_quantity`) | **I** | Un designer ne pose pas de réglage par occurrence (ADR-0002) | 8 tests de `test_cost_engine.py` marqués « chemin », mêlés au CO₂ |
| `engine.py` : CO₂ (`_own_unit_co2`, `_co2_path_adjustments`, `total_co2`) | **I** | La feature parle de prix seulement | 12 tests de `test_cost_engine.py` |
| `engine.py` : taux horaire par cible (`labour_rate_by_part/_path`, ADR-0016) | **I** | Réglage de scénario | 3 tests de `test_cost_engine.py` |
| `bom.py` : SAV (`after_sales_quantity`, `with_after_sales`) | **I** | Pièces de rechange livrées, sans objet pour une carrosserie | `domain/test_after_sales.py` (4) |
| `prices.py` : `PriceSnapshot`, `FRESH`/`STALE`/`DEGRADED` | **E** | Le prix matière vient d'un snapshot | `application/test_take_snapshot.py`, `test_quarantine.py` |
| `scenario.py` : `CalculationInput` | **E** | Entrée du moteur | via `test_cost_engine.py` |
| `calculation_snapshot.py` (snapshot de calcul nommé, ADR-0014) | **I**, **protégé** | Figer un calcul ; sans effet sur l'import ni sur le prix | `domain/test_calculation_snapshot.py` (6) |
| `text_folding.py` | **R** | Recherche sans accents dans l'arbre | `domain/test_text_folding.py` (1) |

### 1.2 Application (`be/application/`, ≈ 2 650 lignes)

| Élément | Classe | Preuve | Tests |
|---|---|---|---|
| `run_calculation.py` : statut, systèmes, contributeurs, empreinte | **E** | Enveloppe du moteur ; produit le total affiché | `test_run_calculation.py` (18), `scenarios/test_parameterized_calculation.py` (5) |
| `price_resolution.py` : référence × multiplicateur × coefficient d'usine | **E** | Le prix d'une matière passe par ici ; une pièce achetée sans fournisseur lève `NoSupplierForPart` (l. `_sourcing_for`). D'où : l'import doit **recopier les offres** de la version de référence | `test_price_resolution.py` (17) |
| `take_snapshot.py` : snapshot, repli, quarantaine | **E** | Source des prix matière | `test_take_snapshot.py` (11), `test_quarantine.py` (12) |
| `browse_bom.py` : racine, enfants, where-used, recherche | **E** (arbre), **R** (where-used, recherche) | L'arbre de la carrosserie importée | `test_browse_bom.py` (24), `test_real_bom_search.py` (2) |
| `tree_view.py` : deux montants par ligne, marques | **E** | Ligne d'arbre chiffrée | `test_tree_view.py` (17) |
| `scenario.py` : `Scenario`, `ScenarioParameter`, `Sourcing` | **E** | `run_calculation` exige un scénario ; `Sourcing` porte les fournisseurs | indirect |
| `manage_scenarios.py` : créer, dupliquer, supprimer, régler | **R** | La feature n'a besoin que de **créer** un scénario sans réglage par version importée | `test_manage_scenarios.py` (16) |
| `calculation_state.py` : à jour / obsolète, libellé de portée | **R** | Utile à l'écran ; pas au calcul | `test_calculation_state.py` (9) |
| `compare_scenarios.py` | **R** | Donne l'écart entre deux carrosseries, **à une condition** : il refuse deux versions de BOM différentes (l. 55). Le snapshot commun reste exigé, et c'est le bon garde-fou | `scenarios/test_comparison.py` (10) |
| `explain_calculation.py`, `calculation_issues.py` | **R** | Disent d'où vient un montant et quelles pièces manquent de prix. **Aucun écran ne les appelle** (`grep` sur `fe/`) | `test_explain_calculation.py` (15), `TestExplain`, `TestIssues` |
| `freeze_calculation.py` (geler, renommer, comparer des gels, repartir) | **I**, **protégé** | ADR-0014 | `test_freeze_calculation.py` (21) + intégration |
| `recommend_sourcing.py` | **I** | Choisit le fournisseur le moins cher ; n'intervient ni dans l'import ni dans le calcul | `scenarios/test_recommendation.py` (7) + 6 tests de `test_api_workflow.py` |
| `supplier_catalog.py` | **I** | Sert seulement la page Fournisseurs | `test_supplier_catalog.py` (4) |
| `ports.py` | mixte | `BomRepository`, `SourcingRepository`, `PriceSnapshotRepository`, `ScenarioRepository`, `CalculationRepository`, `PriceSource.fetch` : **E**. `PriceSource.history`, `PriceHistory`, `PricePoint` et `PriceSnapshotRepository.history_of` : **I** (courbe de prix). `CalculationSnapshotRepository` : **I**, protégé | — |

### 1.3 Infrastructure et API (`be/infrastructure/`)

| Élément | Classe | Preuve | Tests |
|---|---|---|---|
| `postgres/bom.py`, `sourcing.py`, `snapshots.py`, `scenarios.py`, `calculations.py` | **E** | Persistance du calcul. `bom.py` **lit** seulement : l'import y ajoutera l'écriture | `integration/test_postgres_*` |
| `postgres/calculation_snapshots.py` | **I**, **protégé** | ADR-0014 | `integration/test_postgres_calculation_snapshot*.py` |
| `http_price_source.py` : `fetch` | **E** | Prix matière | `test_http_price_source.py` (7) |
| `http_price_source.py` : `history` | **I** | Courbe de prix | 2 tests de `test_price_simulation.py` |
| `seed_loader.py`, `startup.py`, `__main__.py` | **E** | Chargent le Multipla, base de référence des matières et des fournisseurs. `_reject_if_invalid` et `_price_faults` sont le modèle à suivre pour l'import | `test_seed_loader.py` (15), `test_startup.py` (12) |
| `cached_bom_repository.py` | **R** | Cache de lecture ; une version validée est immuable, donc le cache reste juste après un import | `test_cached_bom_repository.py` (5) |
| `snapshot_cli.py` | **R** | Figer les prix en ligne de commande | — |
| `live_calculations.py` + `POST /calculations/live` | **I** | Mode direct, jamais enregistré (ADR-0015) ; le prix d'une carrosserie doit être **reproductible** | `TestLive` (4) |
| Routes `GET /bom/versions`, `/root`, `/children`, `/parts/{ref}` | **E** | Sélecteur de véhicule et arbre | `test_bom_routes.py` |
| Routes `/where-used`, `/search` | **R** | Navigation | `TestWhereUsedAndSearch`, `TestSearchTotalsAndBounds` |
| Routes `/bom/{v}/suppliers`, `/suppliers/{id}/parts`, `/parts/{ref}/price-history` (`bom_routes.py` l. 81–200) | **I** | Page Fournisseurs | `TestSuppliers` (3), `TestPriceHistory` (3) |
| `POST /scenarios`, `GET /scenarios/{id}`, `POST /calculations`, `GET /calculations/{id}` | **E** | Calculer une version importée | `test_calculation_routes.py` |
| `PATCH /scenarios/{id}` (SAV, taux), `PUT/DELETE …/parameters`, `…/duplicate`, `DELETE /scenarios/{id}` | **R** | Réglages de scénario ; inutiles au designer, mais mêlés aux tests du calcul | `test_scenario_routes.py` (19) |
| `POST /scenarios/compare` | **R** | Écart entre deux carrosseries, à la condition du §1.2 | `test_api_workflow.py::test_compare_endpoint…`, `test_compare_moves_latest_calculation.py` |
| `POST …/recommend-sourcing[/preview]` (`calculation_routes.py` l. 580–658) | **I** | Recommandation | 6 tests de `test_api_workflow.py` |
| `GET /calculations/{id}/aggregated`, `/explain`, `/issues` | **R** | Aucun écran | `TestExplain`, `TestIssues` |
| `POST/GET /price-snapshots`, `…/quarantine` | **E** | Figer les prix ; journal des refus | `test_snapshot_routes.py` (9), `TestFreezePrices` (4) |
| `/calculation-snapshots/*` (6 routes) | **I**, **protégé** | ADR-0014 | `test_calculation_snapshot_routes.py` (21) |

### 1.4 Base (`backend/migrations/`)

| Table / objet | Classe | Remarque |
|---|---|---|
| `bom_version`, `part`, `bom_edge` + clés composites (0001) + gel des versions validées (0003) | **E** | L'import y écrit une version. `seed_checksum` sert l'idempotence (§4.5) |
| `supplier`, `supplier_plant`, `part_supplier` | **E** | Le prix d'une matière exige une offre **dans la version** |
| `price_snapshot`, `price_snapshot_line`, `price_quarantine` + déclencheurs | **E** | Prix matière |
| `scenario`, `scenario_parameter`, `calculation`, `calculation_line`, `calculation_system_total`, `calculation_issue`, `calculation_context_cost` (0002) | **E** / **R** | `calculation_context_cost` ne sert que les surcharges de chemin |
| `calculation_snapshot*` (0004, 0005) | **I**, **protégé** | — |
| Colonnes SAV, `labour_rate` par cible (0006, 0007) | **I** | **Ne pas toucher aux migrations appliquées.** Une colonne inutile ne coûte rien ; une migration de suppression coûte un passage sur base réelle |

### 1.5 Front (`fe/`)

| Élément | Classe | Preuve | Tests |
|---|---|---|---|
| `App.tsx` : sélecteur de véhicule, onglets | **E** | Une carrosserie importée apparaîtra dans le sélecteur ; l'onglet « Fournisseurs » peut devenir « Importer » | `App.test.tsx` (30) |
| `Workspace.tsx`, `Tree`, `TreeNode`, `TreeHeader`, `TreeToolbar`, `tree/useTreeState.ts`, `rowId.ts` | **E** | Arbre chiffré | `TreeNode.test` (29), `TreeTable.test` (10), `TreeKeyboard.test` (8), `useTreeState.test` (18) |
| `Summary.tsx` | **E** | Total et décomposition | `Summary.test` (12) |
| `format.ts`, `quarantine.ts`, `api/client.ts`, `api/types.ts` | **E** | Seul endroit qui arrondit ; statut des prix | — |
| `SearchBar`, `Highlight`, `tree/fold.ts`, `WhereUsed` | **R** | Navigation | `SearchBar.test` (11), `Highlight.test` (2), `fold.test` (6), `WhereUsed.test` (3) |
| `NodePanel.tsx` (réglages fournisseur, usine, prix forcé, main-d'œuvre) | **R** | Inutile au designer ; branché dans `TreeNode` | `TreeNode.test` « panneau de saisie » |
| `ScenarioBar`, `SnapshotHeader`, `FrozenSettings` | **I**, **protégé** | Scénarios et snapshots de calcul | `ScenarioBar.test` (8), une partie d'`App.test` |
| `DecisionDialog.tsx` : `ComparePane`, `SnapshotComparePane` | **R** / protégé | Écart A/B | `DecisionDialog.test` « comparer » (3), « … snapshots » (6) |
| `DecisionDialog.tsx` : `RecommendPane` (l. 390–611) | **I** | Recommandation | `DecisionDialog.test` « recommander » (2) |
| `SuppliersPage.tsx`, `PriceChart.tsx` | **I** | Page Fournisseurs | `SuppliersPage.test` (4) |
| `PriceModeBar.tsx` (direct / snapshot) | **I** (partie direct) | « Figer les prix maintenant » y vit aussi et reste **E** | `App.test` : 2 tests |
| `AfterSalesToggle.tsx`, `LabourRateInput.tsx` | **I** | Réglages de scénario | `AfterSalesToggle.test` (3) |
| `api.deleteParameter`, `api.priceSnapshots` | **I** | Jamais appelées hors de `client.ts` (`grep '\.m('`) | aucun |

### 1.6 Données, outils, documents

| Élément | Classe | Remarque |
|---|---|---|
| `seeds/` Multipla + `tools/bom_generator` | **E** | Le Multipla fournit les matières, les pièces achetées, leurs prix et leurs fournisseurs, que l'import référence. Le contrôle de déterminisme est en CI |
| `price-api/` | **E** | Source des prix matière |
| `seeds/valhalla/*`, `tools/valhalla_import` (≈ 1 680 lignes) | **I** | Trois autres véhicules ; `test_valhalla_seeds.py` (6) ; 3 catalogues servis par `price-api` ; `--check` en CI |
| `tools/price_history.py` | **I** | Génère `price-api/data/price_indices.json`, **lu par le simulateur** : à garder tant que le simulateur l'est |
| ADR 0001, 0003–0005, 0007, 0008, 0011, 0013, 0015 | **E** | Fondent le calcul et l'import |
| ADR 0002, 0006, 0009, 0010, 0016 | **R** | Toujours appliqués par le code gardé |
| ADR 0012, 0014 | **I** / protégé | Comparaison et recommandation ; snapshot de calcul |
| `docs/analyse-calcul-cout-carbone.md`, `docs/scenarios.md`, `docs/plan-vues.md` (non suivi par git) | **I** | `plan-vues.md` §4.5 proposait déjà un « Designer 3D » avec masse = volume × densité : repris ici en glTF (§4.6) |

---

## 2. Est-ce vraiment utile ? Est-ce qu'on peut faire plus simple ?

### 2.1 Pour chaque élément E ou R

| Élément | Plus simple ? | Coût |
|---|---|---|
| Moteur (`engine.py`) | **Non pour la feature** : il fait déjà « masse × prix matière + pièces ». Retirer chemin, CO₂ et taux par cible enlèverait ≈ 200 lignes, mais réécrirait ≈ 25 tests dans la zone protégée | M, risque élevé, gain nul pour la feature → **ne pas faire** |
| `price_resolution.py` | Non. Le multiplicateur fournisseur et le coefficient d'usine valent ce que la version de référence déclare ; l'import recopie ses offres | — |
| Scénario obligatoire pour calculer | **Oui** : l'import crée lui-même un scénario sans réglage sur la version créée. Pas d'écran de scénario pour le designer | S |
| Comparaison A/B | **Oui** : lever le refus « versions de BOM différentes » dans `compare_calculations`, et garder le refus « snapshots différents ». Les deltas sont déjà par `part_ref`, et l'aileron apparaît comme une ligne de A = 0 | S, mais contredit une condition d'ADR-0012 (au statut « proposé ») : une ligne dans l'ADR de la feature |
| Calcul de l'écart | Variante plus simple encore : l'écran affiche `total(B) − total(A)` servi par une route. **Pas d'arithmétique dans le navigateur** : la soustraction doit rester côté serveur | S |
| `NodePanel` | Le masquer sur une version importée suffit ; le supprimer casserait les tests de saisie | S |
| Lecteur glTF | **Bibliothèque standard** : un GLB, c'est un en-tête de 12 octets puis un bloc JSON (`struct.unpack` + `json.loads`). Pas de `trimesh` ni de `pygltflib` | S, aucune dépendance |
| Envoi du fichier | **Corps brut** (`application/octet-stream`, `await request.body()`), pas de formulaire multipart : FastAPI exigerait `python-multipart`, une dépendance de plus | S |
| Écriture d'une version | Réutiliser la validation de `seed_loader` (`validate_bom` + `_price_faults`), et écrire par `INSERT` dans une transaction. La version passe `validated_at` dans la même transaction | M |

### 2.2 Constats `/ponytail-audit` (rangés du plus gros gain au plus petit)

> **Décision du 06/10** : seul le code mort au sens strict est supprimé (§3). Les constats
> ci-dessous restent à titre d'information sur la complexité ; ce ne sont pas des suppressions.

Ces constats portent sur la complexité seulement. Ceux marqués **[V]** touchent au prix, à
l'arbre/BOM ou aux snapshots : ils demandent votre validation.

1. delete `tools/valhalla_import` + `seeds/valhalla/` + `test_valhalla_seeds.py` (≈ 1 850 lignes de code et de test, plus les données). Remplacement : rien ; le Multipla suffit comme base. [`tools/valhalla_import/`] **[V]**
2. delete `RecommendPane` + `recommend_sourcing.py` + 2 routes + types (≈ 600 lignes). Remplacement : rien. [`be/application/recommend_sourcing.py`, `fe/components/DecisionDialog.tsx:390`]
3. delete la page Fournisseurs : `SuppliersPage`, `PriceChart`, `supplier_catalog.py`, 3 routes, `PriceSource.history`, `history_of` (≈ 650 lignes). Remplacement : rien. [`fe/components/SuppliersPage.tsx`]
4. yagni surcharges de chemin dans le moteur (≈ 180 lignes + table `calculation_context_cost`). Une seule portée suffirait au designer. [`be/domain/engine.py:257`] **[V]**
5. delete CO₂ de bout en bout (moteur, contributeurs, synthèse, comparaison). Remplacement : rien pour la feature. [`be/domain/engine.py:110`] **[V]**
6. delete mode direct : `LiveCalculations`, `WithLiveCalculations` (enveloppe qui délègue par `__getattr__`), route, bouton. Remplacement : « Figer les prix maintenant ». [`be/infrastructure/live_calculations.py`] **[V]**
7. delete `purchase_currency` : accepté, persisté, **sans effet** sur le prix (README, « Devises »). Flexibilité morte. [`be/application/scenario.py:31`] **[V]**, car copié dans les snapshots de calcul
8. delete SAV : `after_sales_quantity`, `with_after_sales`, `AfterSalesToggle`. [`be/domain/bom.py:47`] **[V]**
9. delete taux horaire par cible (ADR-0016). Remplacement : le taux du scénario. [`be/domain/engine.py:228`] **[V]**
10. reuse `SCALE = Decimal("0.000001")` défini 4 fois. Remplacement : `engine.SCALE` / `price_resolution.to_scale`. [`be/infrastructure/api/bom_routes.py:31`, `calculation_routes.py:56`, `price_resolution.py:28`]
11. reuse `tree_view.path_quantity` refait `engine._path_quantity`. Remplacement : une seule fonction publique dans le domaine. [`be/application/tree_view.py:56`] **[V]**
12. delete `api.deleteParameter`, `api.priceSnapshots` : jamais appelées. [`fe/api/client.ts`]
13. shrink `Tree.tsx` réexporte `rowId`. Remplacement : importer `./rowId` directement. [`fe/components/Tree.tsx:20`]

Dépendances : aucune à retirer. Le backend en a 3 (FastAPI, uvicorn, psycopg) et le front 2
(React, React DOM). La feature n'en ajoute **aucune** (§2.1).

net : ≈ −1 250 lignes sans validation (constats 2, 3, 10, 12, 13), ≈ −3 500 avec validation ;
−0 dépendance possible.

---

## 3. Nettoyage retenu : le code mort au sens strict

**Définition.** Un élément (fonction, méthode, classe, type, constante, route, fichier) est
**mort** s'il n'est atteint par **aucun point d'entrée** du système autrement que par ses propres
tests. Les points d'entrée sont :

- un écran ;
- une route appelée ;
- la CLI ;
- la CI ;
- le chargement des données ;
- le Docker Compose.

Une fonction utile **plus tard** n'est pas morte si elle est branchée aujourd'hui. Une fonction
inutile **à la feature** non plus. Les éléments classés **I** au §1 et les constats 1 à 9 du §2.2
restent donc en place. Ils sont conservés pour mémoire ; ce ne sont pas des suppressions.

**Méthode.** Le relevé est systématique :

- pour chaque fonction, méthode et classe Python de `backend/src`, `tools` et `price-api`, on
  compte les références hors de sa propre définition et hors des tests ;
- même relevé pour chaque export TypeScript de `frontend/src`, et pour chaque méthode de
  `api/client.ts` (appels `.méthode(` hors tests) ;
- on retire les faux positifs : gestionnaires enregistrés par décorateur, types utilisés dans le
  même fichier.

**Limites.** Une méthode qui porte le même nom qu'une méthode vivante échappe au relevé. Les
imports inutilisés et le CSS ne sont pas couverts : aucun linter n'est installé.

### 3.1 Supprimé

| Élément | Action | Fichiers | Tests supprimés | Tests modifiés | Risque |
|---|---|---|---|---|---|
| `CalculationResult.is_incomplete` | supprimer | `be/domain/engine.py:71` (3 lignes) | aucun | `domain/test_cost_engine.py` l. 203 et `test_real_bom_control_values.py` l. 107 : `result.is_incomplete` devient `result.parts_without_price` (même valeur de vérité) | Nul. Zone du moteur : **validé** par votre choix de l'option « mort au sens strict seul », qui le nommait. À contredire si ce n'était pas l'intention |
| `supplier_by_id` | supprimer | `tools/valhalla_import/suppliers.py:139` (5 lignes) | aucun | aucun | Nul ; `python -m tools.valhalla_import --check` le prouve |
| `Bom.parents_of` du générateur | supprimer | `tools/bom_generator/model.py:74` (2 lignes) | aucun | aucun | Nul ; `python -m tools.bom_generator --check` le prouve (sortie identique à l'octet près) |
| `api.deleteParameter` | supprimer | `fe/api/client.ts` | aucun | aucun | Nul. La route `DELETE …/parameters/{id}` reste (§3.2) |
| `api.priceSnapshots` | supprimer | `fe/api/client.ts` | aucun | aucun | Nul. La route `GET /price-snapshots` reste (§3.2) |
| type `ApiError` | supprimer | `fe/api/types.ts:335` | aucun | aucun | Nul |

### 3.2 Gardé : brique sans appelant, pas morte au sens retenu

Ces routes ne sont appelées par aucun écran. Mais elles sont au contrat public
(`docs/api.md`), et le README prévoit leur écran (« Expliquer un montant à l'écran », « Lister les
prix de repli », « Renommer un snapshot »).

| Route | Cas d'usage derrière |
|---|---|
| `GET /calculations/{id}/explain` | `explain_calculation.py` |
| `GET /calculations/{id}/issues` | `calculation_issues.py` |
| `GET /calculations/{id}/aggregated` | — |
| `GET /price-snapshots` | `PriceSnapshotRepository.list_all` |
| `DELETE /scenarios/{id}/parameters/{id}` | `ScenarioRepository.delete_parameter` |
| `PATCH /calculation-snapshots/{id}` | `rename_snapshot` (zone protégée) |

### 3.3 Proposition initiale, écartée

La version précédente de ce document proposait de supprimer la recommandation de sourcing et la
page Fournisseurs (32 tests). C'est **écarté** : ces deux fonctions sont branchées à l'écran,
donc vivantes. Les constats du §2.2 restent comme information sur la complexité.

---

## 4. Cadrage de la feature (Multipla)

### 4.1 Le métier, vérifié

| Constat | Source |
|---|---|
| L'**ingénieur coût** lit les modèles CAO et la nomenclature d'ingénierie pour estimer le prix des pièces. Il soutient le « design-to-cost » et influence architecture et matériaux dès les premières phases. Aston Martin recrute sur ce poste | [Aston Martin](https://careers.astonmartin.com/cw/en/job/511712/cost-engineer), [Segula](https://smartrecruiters.com/SegulaTechnologies/744000032731526) |
| aPriori chiffre directement depuis le modèle CAO 3D (tôlerie comprise), avec le détail matière, main-d'œuvre et frais. Un des cinq plus grands constructeurs l'utilise | [aPriori](https://www.apriori.com/wp-content/uploads/2022/08/aPriori-Manufacturing-Cost-Models-for-Auto-DS-062922-V11.pdf), [annonce](https://www.apriori.com/announcement/top-5-automaker-chooses-apriori-to-accelerate-cost-reduction-goals/) |
| Teamcenter Product Cost Management ouvre le modèle 3D dans un visualiseur et en extrait épaisseur, surface et volume. Quand l'ingénieur modifie la pièce, le chiffrage se met à jour | [Siemens](https://blogs.sw.siemens.com/teamcenter/new-teamcenter-product-cost-management-capabilities/) |
| Le studio de style produit des surfaces sans épaisseur ; l'ingénierie en fait des pièces. La caisse en blanc se conçoit surtout dans CATIA | [cadcrowd](https://www.cadcrowd.com/service/2672-vehicle-development-styling-class-a-surfacing), [3DS](https://www.3ds.com/fileadmin/PRODUCTS-SERVICES/CATIA/PDF/CATIA-ICEM-Shape-Design-Brochure.pdf) |
| La caisse en blanc pèse 20 à 25 % du véhicule. Acier HLE ≈ −10 %, aluminium −30 à −40 %, carbone ≈ −50 % de masse, contre un surcoût. Ces variantes s'évaluent tôt par modélisation des coûts | [WorldAutoSteel](https://www.worldautosteel.org/?p=1155), [ACTA 2017](https://acta.fih.upt.ro/pdf/2017-2/ACTA-2017-2-20.pdf), [SAE 2011-01-0767](https://saemobilus.sae.org/content/2011-01-0767) |
| Le format de visualisation de l'industrie est le **JT** (ISO 14306), standard de fait chez GM | [ISO](https://www.iso.org/es/contents/data/standard/08/92/89233.html), [gfxspeak](https://gfxspeak.com/archives/jt-accepted-as-first-iso-standard-for-lightweight-3d-product-information/) |

**À dire en soutenance** :

- notre chiffre est l'**impact matière** d'une variante (matière + fixations + main-d'œuvre déjà
  connue). Ce n'est pas un coût de fabrication complet : ni procédés, ni outillage, ni volumes.
  Or l'outillage compte (l'acier n'est rentable qu'au-delà d'environ 100 000 caisses par an,
  source ACTA ci-dessus) ;
- le glTF tient le rôle du JT pour le web ; l'ADR-0017 justifie ce choix.

### 4.2 Qui fait quoi

| Qui | Ce qu'il fait |
|---|---|
| **Ingénieur carrosserie** | Part du modèle du véhicule (téléchargeable). Modifie ou ajoute des pièces, chacune étant un **objet fermé, à l'échelle réelle** (mètres), **avec épaisseur**. Nomme le **matériau** d'après la matière (`MAT-ALU-SHEET`). Renseigne `ref` (obligatoire) et `parts` (fixations, facultatif) en propriétés personnalisées. Exporte en `.glb` |
| **Ingénieur coût, achats, projet** | Ouvrent la variante : vue 3D liée à l'arbre, pièces modifiées colorées, écart de coût et de masse |
| **Métier** (une fois) | Relit la table des densités (§4.5) |
| **L'outil** | Mesure, vérifie, calcule la masse, crée et gèle la variante, la chiffre sur le snapshot de prix du Multipla, renvoie l'écart |

### 4.3 Le modèle 3D d'un véhicule

- **Stockage** : une nouvelle table `bom_model` (`bom_version_id` en clé, `glb bytea`, `sha256`,
  `source` = `generated` ou `imported`, `created_at`). C'est une table **à part** : rattacher un
  modèle à une version validée ne touche ni `part`, ni `bom_edge`, ni `part_supplier`, que le
  déclencheur 0003 gèle. Un modèle rattaché ne se modifie pas : même déclencheur que les
  snapshots.
- **Lecture** : `GET /api/v1/bom/{version}/model` renvoie le GLB (`model/gltf-binary`), ou un 404
  `MODEL_NOT_FOUND`. C'est le cas des Valhalla pour l'instant ; l'écran dit alors « pas de modèle
  3D pour ce véhicule ».
- **Taille** : la maquette du Multipla compte environ 60 objets simples, soit quelques dizaines
  de Ko.

### 4.4 La maquette générée (Multipla)

Un script déterministe, `tools/body_model`, avec `--check` en CI comme les autres générateurs :

- **une forme par pièce de carrosserie à matière déclarée** : 26 pièces, soit **51 objets**,
  puisqu'une pièce montée deux fois donne deux objets qui partagent le même maillage ;
- **placées à la main** dans une table relue (capot devant en haut, pavillon, côtés gauche et
  droit, portes, hayon, pare-chocs, passages de roue…), pour une silhouette de Multipla
  reconnaissable ;
- **dimensionnées pour une masse exacte** : le script cherche les dimensions en float32 telles
  que `arrondi₁₀⁻⁶(volume × densité)` = masse de la nomenclature. L'arrondi est celui du
  projet, pas une nouvelle règle. La précision du float32 rend la recherche toujours possible
  en jouant sur les trois côtés ;
- les pièces achetées visibles (pare-brise, rétroviseurs, optiques) sont des **objets de décor**,
  sans `extras.carcost` : affichées en gris, ignorées par l'import.

DoD clé : pour **chacune** des 26 pièces, la masse mesurée par le lecteur glTF est égale à la
masse de la nomenclature. Réimporter la maquette ne change rien (§4.6).

### 4.5 Densités (valeurs usuelles, synthétiques, à relire)

Une colonne `part.density_kg_m3` (migration 0008) est ajoutée, écrite par le générateur pour les
matières au kg. Le champ `Part.density_kg_m3: Decimal | None = None` est ajouté au domaine, ainsi
que `Part.material_ref`, déjà présent en base mais non lu.

| Matière | kg/m³ |
|---|---|
| `MAT-STEEL-SHEET` | 7 850 |
| `MAT-STAINLESS-SHEET` | 7 700 |
| `MAT-ALU-SHEET` | 2 700 (5754 : 2 670, à trancher) |
| `MAT-ABS-GRANULE` | 1 050 |
| `MAT-PP-GRANULE` | 900 |
| `MAT-PC-GRANULE` | 1 200 |
| `MAT-GLASS-FLOAT` | 2 500 |
| `MAT-EPDM-RUBBER` | 1 200 |
| autres matières au kg | à compléter, même règle |

### 4.6 Ce que fait un import

L'import s'applique à la version **ouverte**. Le fichier est un glTF 2.0 (`.glb`).

| Objet du modèle | Effet |
|---|---|
| `ref` = pièce **fabriquée** existante à `material_ref` renseigné (`CAR-HOOD-SHELL`) | L'arête vers la matière est remplacée par la matière du modèle, de quantité = masse mesurée. `mass_kg` et `material_ref` suivent. Main-d'œuvre, fixations, parents et quantités sont **inchangés** |
| `ref` = pièce **nouvelle** | Pièce fabriquée créée sous `CAR-ASSY`, quantité = **nombre d'objets** qui la portent, 0 min de main-d'œuvre, une arête vers sa matière et une par fixation |
| Plusieurs objets avec la même `ref` | Ce sont ses **emplacements de montage** (glossaire §1). Ils doivent partager le **même maillage**, sinon refus. La masse est celle **d'une** pièce |
| Objet sans `extras.carcost` | Décor, ignoré |
| Pièce de la version absente du modèle | Inchangée |
| **Aucune masse ni matière ne change** (à l'échelle 10⁻⁶) | **Pas de variante créée** : la réponse est « aucun changement », écart 0 |

La variante créée a les propriétés suivantes :

- `id` = `<parente>+<8 caractères du SHA-256>` ;
- `parent_version_id` (migration 0008) ;
- `is_synthetic = true` ;
- `generator_version = "body-import/1"` ;
- **validée et gelée** dans la transaction ;
- son modèle est rangé dans `bom_model`.

Elle reprend les pièces achetées et les offres de la parente : un import **ne crée jamais de pièce
achetée**, et n'invente donc jamais de prix. Le même fichier sur la même parente donne la même
variante (200).

**Prix** : la variante est chiffrée sur le **dernier snapshot de prix du Multipla**, origine de
toute la filiation. **Écart** : `compare_calculations`, sans son refus « versions différentes » et
avec le refus « snapshots différents » conservé. Le calcul est fait côté serveur. Ces deux points
s'écartent d'ADR-0015 et d'ADR-0012, ce que l'ADR-0017 dit.

**Mesure** (adaptateur, bibliothèque standard seule) :

- triangles de `POSITION`, avec ou sans indices, passés par la matrice monde du nœud ;
- volume = Σ p₁·(p₂×p₃)/6, calculé **en décimal exact** à partir des float32 (un `float` Python
  perdrait des chiffres sur le triple produit) ;
- **fermé** = chaque arête est partagée par exactement deux triangles ;
- volume ≤ 0 : refus ;
- `extensionsRequired` non vide (Draco, meshopt) : refus.

### 4.7 La vue 3D

| Élément | Choix |
|---|---|
| Place | Zone de droite de l'espace de travail, avec un onglet « Synthèse » / « 3D ». L'arbre reste visible (règle de `Workspace.tsx`) |
| Bibliothèque | `three`, une seule dépendance npm, justifiée au commit. **Chargée à la demande** (`import()`) : le reste de l'écran ne paie rien. Poids ≈ 150 à 200 Ko compressé, ordre de grandeur à mesurer au build |
| Clic sur une pièce | Sélectionne la ligne de l'arbre : on déplie le premier chemin, avec la recherche existante |
| Sélection d'une ligne | Surligne **tous** les objets de cette pièce, donc toutes ses occurrences |
| Variante | Les pièces modifiées ou nouvelles sont colorées. La liste vient de l'API (écarts par pièce), **pas** d'une comparaison faite dans le navigateur |
| Tests | jsdom n'a pas de WebGL : on teste la logique (référence ↔ sélection, ensemble coloré) à part ; le rendu se vérifie dans un navigateur |
| Mémoire | Géométries et matériaux libérés au démontage |

### 4.8 Démonstration et jeu de test chiffré

**Convention.** Snapshot **fixe** = prix de référence du catalogue Multipla, ramenés à l'unité ;
**vraies** offres par défaut (`seeds/suppliers.json`) ; 42 €/h. Les chiffres sont **vérifiés avec
`domain.engine.compute`** sur la vraie nomenclature, en mémoire. En démonstration, les prix figés
à l'instant donneront d'autres valeurs, mais la même mécanique.

| Prix unitaire | Calcul | Résultat |
|---|---|---|
| `MAT-ABS-GRANULE` | 2,05 × 1,016900 × 0,962 | 2,005428 €/kg |
| `MAT-STEEL-SHEET` | 1,10 × 1,065860 × 0,962 | 1,127893 €/kg |
| `MAT-ALU-SHEET` | 3,10 × 0,983560 × 0,962 | 2,933173 €/kg |
| `FIX-M8-20` | 6,20 / 100 × 0,958300 × 0,868 | 0,051572 €/pce |

**Multipla (A)** : total 13 285,661001 17 €, ligne Carrosserie 2 605,504901 €.

**`aileron.glb`** : la maquette, plus un objet `BODY-SPOILER` (pavé de 1,20 × 0,25 × 0,010 m,
`MAT-ABS-GRANULE`, `parts = {FIX-M8-20: "4"}`).

| Grandeur | Calcul | Valeur |
|---|---|---|
| Masse | 0,003 m³ × 1 050 | 3,15 kg |
| **Écart** | 3,15 × 2,005428 + 4 × 0,051572 = 6,3170982 + 0,206288 | **+6,5233862 €** |
| Total B | moteur | 13 292,184387 37 € |
| `FIX-M8-20` (pièce partagée) | quantité cumulée | 204 → **208** |

**`capot-alu.glb`** : la maquette, dont l'objet `CAR-HOOD-SHELL` passe au matériau
`MAT-ALU-SHEET`, **même géométrie**.

| Grandeur | Calcul | Valeur |
|---|---|---|
| Volume du capot de la maquette | 11,2 / 7 850 | 0,001426 752 m³ |
| Masse aluminium | arrondi₁₀⁻⁶(11,2 × 2 700 / 7 850) | **3,852229 kg** (−7,347771 kg) |
| Coût matière avant | 11,2 × 1,127893 | 12,6324016 € |
| Coût matière après | 3,852229 × 2,933173 | 11,299254 092617 € |
| **Écart** | | **−1,333147 507383 €** |
| Total C | moteur | 13 284,327853 66 € |

Le message pour le métier : l'aluminium coûte 2,6 fois plus cher au kilo, mais le même capot
pèse 2,9 fois moins. Il devient **moins cher et plus léger**.

**Maquette réimportée telle quelle** : « aucun changement », pas de variante, écart **0,00 €**.

**Déroulé en trois minutes** :

1. ouvrir le Multipla, puis l'onglet 3D ; cliquer sur le capot, et l'arbre suit ;
2. importer `capot-alu.glb` : le capot est coloré, −1,33 €, −7,35 kg ;
3. importer `aileron.glb` : l'aileron apparaît, +6,52 €, et la vis M8 passe à 208 ;
4. réimporter la maquette : « aucun changement » ;
5. importer `capot-surface.glb` : refus `MESH_NOT_CLOSED`, qui nomme l'objet.

### 4.9 Cas d'erreur

Toutes les fautes sont rendues **en une fois** (422), avec l'objet et la référence. Rien n'entre en
base si une seule faute existe.

| Cas | Code |
|---|---|
| Pas un glTF 2.0 lisible ; aucun objet `carcost` | `INVALID_MODEL_FILE` |
| Draco, meshopt | `UNSUPPORTED_EXTENSION` |
| `ref` ou matériau manquant | `MISSING_SPEC` |
| Tôle en surface | `MESH_NOT_CLOSED` |
| Normales inversées | `NON_POSITIVE_VOLUME` |
| Matière inconnue, ou sans densité (`MAT-PAINT-BASE`, au litre) | `UNKNOWN_MATERIAL`, `MATERIAL_WITHOUT_DENSITY` |
| Fixation inconnue ou fabriquée | `UNKNOWN_PART`, `NOT_PURCHASED` |
| `ref` d'une pièce achetée (`CAR-DOOR-HINGE`) ou d'un ensemble sans matière (`CAR-BIW-ASSY`) | `REF_IS_PURCHASED`, `NOT_A_MATERIAL_PIECE` |
| Objets de même `ref` avec des maillages différents | `OCCURRENCES_DIFFER` |
| Même fichier deux fois | 200, même variante, écart 0 |
| Aucun snapshot du Multipla | La variante est créée ; le calcul répond `NO_PRICES`, jamais 0 € |

---

## 5. Ce qu'il faut changer pour les Valhalla

Constat sur `seeds/valhalla/hybride` (les trois sont construites pareil) : **aucune pièce de
carrosserie n'a de matière déclarée** (0, contre 26 sur le Multipla). Exemple de la monocoque
`VALH-BOM-0006` (74,2 kg) :

- des peaux carbone **achetées à la pièce** (`PEAU-EXT`, `PEAU-INT`, `RENFORT`, `ATTACHE`) ;
- 8,9 kg de préimprégné et 3,7 kg de nid d'abeille, dimensionnés **par part de prix** (12 % et
  5 %, `tools/valhalla_import/detail.py` l. 291), et non par la masse.

Changer la forme n'y changerait donc rien au prix.

| # | Changement | Où | Pourquoi |
|---|---|---|---|
| V1 | Pour les pièces de carrosserie (catégories `STRUCTURE-CARROSSERIE`, `AERODYNAMIQUE-EXTERIEUR`), produire une **matière dominante au kg** dont la quantité suit la **masse** de la pièce, et renseigner `material_ref` | `detail.py` (familles « composite ») | Sans cela, la géométrie n'a aucune prise sur le coût |
| V2 | Composite sandwich (préimprégné + nid d'abeille, deux matières) : soit **une matière équivalente** (« sandwich carbone/aramide », densité équivalente), soit autoriser **plusieurs matières par pièce** avec une fraction volumique déclarée dans le modèle | `detail.py`, règle d'import | La règle « une pièce = une matière » ne couvre pas un sandwich. Recommandation : la matière équivalente, plus simple et suffisante |
| V3 | **Garder le prix de la source au centime** : les peaux achetées absorbent le reste du prix, comme aujourd'hui | `detail.py` | `test_the_hybrid_keeps_every_price_of_the_source_file` l'exige ; à recaler, sans le supprimer |
| V4 | Densités des matières Valhalla : préimprégné carbone cuit ≈ 1 550, billette alu 7075 ≈ 2 810, et la densité équivalente du sandwich | générateur | Masse calculée |
| V5 | **Une maquette par véhicule**. Les trois Valhalla ont la même caisse : une seule table de placement, et une correspondance par suffixe de référence (`VALH-BOM-0006` ↔ `VALT-BOM-0006`) | `tools/body_model` | Moins de travail, cohérent |
| V6 | Régénérer `seeds/valhalla/*`, puis lancer `--check` et `test_valhalla_seeds.py` | CI | Déterminisme |

Effort : M. Risque : on touche des données dont le README dit déjà qu'elles sont « à relire ».
**Règle métier absente** à trancher au moment de faire : la densité équivalente du sandwich.
D'ici là, les Valhalla affichent « pas de modèle 3D pour ce véhicule », et tout le reste
fonctionne comme aujourd'hui.

---

## 6. Découpage en deux `/deliver`

### A : supprimer le code mort au sens strict

| Tâche | Definition of Done |
|---|---|
| A.1 Les 6 éléments du §3.1 | `grep -rnw "is_incomplete\|supplier_by_id\|parents_of\|deleteParameter\|priceSnapshots\|ApiError"` ne renvoie plus rien. **Aucun test supprimé** : le nombre de tests est inchangé ; seules les 2 assertions du §3.1 changent |
| Contrôles | `python -m pytest backend` est vert, **intégration comprise** (48 non sautés). `tools.bom_generator --check` et `tools.valhalla_import --check` sont verts. `npx tsc --noEmit` et `npm test` sont verts. 26 écritures interdites refusées |

### B : modèle 3D et import de variante (Multipla)

| Tâche | Definition of Done |
|---|---|
| B.0 ADR-0017 | **Avant le code**. Il couvre : personas ; glTF au lieu de JT ; masse mesurée ; densités ; maquette générée ; variante gelée et `parent_version_id` ; `bom_model` ; snapshot du Multipla (écart à ADR-0015) ; comparaison entre versions (écart à ADR-0012) ; main-d'œuvre 0 et CO₂ masqué ; limite « impact matière, pas coût complet » |
| B.1 Données | Migration 0008 (`part.density_kg_m3`, `bom_version.parent_version_id`, table `bom_model` et son déclencheur d'immuabilité) passée sur un vrai Postgres, base existante comprise. Le générateur écrit les densités et `--check` est vert. `Part` lit `material_ref` et `density_kg_m3`. Les contraintes tiennent ; le compte des écritures interdites refusées est mis à jour **et justifié** |
| B.2 Lecteur glTF | Tests d'abord, sur des GLB construits dans le test : pavé 0,003 m³ ; `scale [2,1,1]` donne 0,006 ; deux nœuds sur un même maillage ; face manquante donne `MESH_NOT_CLOSED` ; normales inversées ; Draco. Volume en décimal exact. Bibliothèque standard seule ; `pyproject.toml` inchangé |
| B.3 Maquette du Multipla | `tools/body_model` est déterministe, avec `--check` en CI. 26 pièces, 51 objets, plus du décor. **Pour chaque pièce, la masse mesurée par B.2 est égale à la masse de la nomenclature.** Elle est chargée dans `bom_model` avec le jeu de données |
| B.4 Cas d'usage `import_body` | Tests d'abord, sur la **vraie** nomenclature à prix fixes (§4.8). Le capot alu donne **−1,333147507383 €** ; l'aileron **+6,5233862 €** et `FIX-M8-20` à **208** ; la maquette réimportée donne « aucun changement » ; le même fichier deux fois donne la même variante. Chaque code du §4.9 a un test, et les fautes multiples sont rendues ensemble |
| B.5 Postgres | Tests d'intégration : la variante est gelée ; son modèle est immuable ; un import refusé ne laisse **aucune** ligne ; la parente est inchangée |
| B.6 Routes | `POST /api/v1/bom/{version}/body-imports` (corps brut) : 201, 200 et 422. `GET /api/v1/bom/{version}/model` : 200 et 404. Montants en chaînes |
| B.7 Vue 3D | `three` chargé à la demande. Le lien clic ↔ arbre et les pièces colorées sont testés en logique. **Piloté dans un navigateur** avec les fichiers du §4.8. Ce qui n'a pas pu être vérifié est dit |
| B.8 Fichiers de démonstration | `aileron.glb`, `capot-alu.glb`, `capot-surface.glb`, dérivés de la maquette par le même script. README : démonstration et « ce qu'il reste à faire » (Valhalla §5, commentaires par pièce) |

---

## 7. Compte rendu de la session du 06/10/2026

### Ce qui a été fait

1. **Audit** de tout le code livré : domaine, application, API, base, front, données, ADR et
   tests. Chaque élément est classé (essentiel, réutilisable, inutile pour la feature), avec ses
   preuves et ses tests (§1).
2. **Simplicité** : pour chaque élément utile, est-ce qu'on peut faire plus simple ? Le constat
   central : le moteur fait déjà « masse × matière + pièces ». S'y ajoute un audit
   `/ponytail-audit` de la complexité (§2).
3. **Nettoyage** : une première proposition (supprimer recommandation et Fournisseurs) a été
   **écartée**, parce que ces fonctions sont branchées. La décision est de supprimer **le code
   mort au sens strict**, défini et relevé systématiquement : 6 éléments, 0 test supprimé (§3).
4. **Cadrage** : format, qui fait quoi, stockage, maquette, règles d'import, vue 3D, erreurs
   (§4). Le métier a été vérifié par des sources (§4.1). Le plan pour les Valhalla est au §5.
5. **Chiffres vérifiés** : toute la démonstration a été recalculée à la main, puis avec le vrai
   moteur sur la vraie nomenclature (§4.8).
6. **Corrections faites en cours de route** :
   - une règle « doublon » qui aurait refusé une pièce montée deux fois ;
   - une règle de matière qui aurait laissé passer `CAR-BIW-ASSY` ;
   - un décompte de tests ;
   - le chiffrage du capot, refait sur la géométrie de la maquette.

### Ce qui a été vérifié, et ce qui ne l'a pas été

- **Vérifié** : 570 tests backend hors intégration passent ; calculs du moteur en mémoire ;
  relevé du code mort ; structure des données Multipla et Valhalla.
- **Non vérifié** : les 48 tests d'intégration Postgres, la suite front, l'écran. Rien n'a été
  développé.
- **Aucun fichier du projet modifié** hors de ce document, qui **n'est pas commité**.

### Pour la suite

1. Relire ce document, en particulier §0 (décisions), §4.5 (densités) et §4.8 (démonstration).
2. Lancer `/deliver` **A** : le code mort, sur une branche.
3. Lancer `/deliver` **B** en commençant par **B.0** (ADR-0017). Ordre : B.1 → B.2 → B.3, puis
   B.4 → B.5 → B.6 → B.7 → B.8. B.2 et B.3 peuvent avancer en parallèle de B.1.
4. Plus tard : les Valhalla (§5), les commentaires par pièce, et la densité du sandwich carbone
   (règle métier à trancher).
