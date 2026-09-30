# Contrats d'API — 3istor

- **Date** : 2026-09-22
- **Statut** : proposé — aucune implémentation n'a commencé
- **Base** : `/api/v1`
- **Décisions qui contraignent ce contrat** : [ADR-0002](adr/0002-portee-des-parametres-piece-ou-chemin.md)
  (portée), [ADR-0003](adr/0003-snapshot-de-prix-persiste-et-immuable.md) (snapshot),
  [ADR-0008](adr/0008-mode-de-valorisation-exclusif.md) (valorisation),
  [ADR-0009](adr/0009-depliage-paresseux-du-dag-a-l-ecran.md) (dépliage),
  [ADR-0010](adr/0010-prix-decompose-fournisseur-et-usine.md) (décomposition du prix),
  [ADR-0011](adr/0011-decimal-exact-et-arrondi-a-l-affichage.md) (précision)

---

## 1. Conventions

### 1.1 L'identité d'une ligne d'arbre est son chemin

Une pièce partagée apparaît à plusieurs endroits. Une référence ne désigne donc pas une ligne de
l'arbre ; **un chemin, si**.

```
path = VEH-MULTIPLA-16V/GMP-ASSY/ENG-BLOCK-ASSY/FIX-M6-16
```

Les références sont garanties `[A-Z0-9-]+` par le générateur, ce qui rend un chemin transportable
dans une URL sans échappement. Le chemin **inclut la racine**. Un chemin de longueur 1 désigne la
racine elle-même.

### 1.2 Montants et grandeurs

```json
{ "amount": "39.742800", "currency": "EUR" }
{ "kg_co2e": "0.310000" }
```

- Un montant est une **chaîne décimale à 6 décimales**, jamais un nombre flottant JSON (ADR-0011).
- Le front **arrondit pour afficher** (2 décimales, `ROUND_HALF_UP`) : c'est du formatage. Il
  n'additionne, ne multiplie et ne convertit jamais.
- Toute quantité est accompagnée de son unité. Un nombre sans unité n'est pas renvoyé.

### 1.3 Deux montants qu'il ne faut jamais confondre

Sur un graphe, « la contribution d'une pièce » recouvre deux grandeurs différentes. L'API les nomme
séparément, et ne renvoie jamais l'une sous le nom de l'autre.

| Champ | Ce que c'est | Se somme ? |
|---|---|---|
| `unit_cost` | Coût unitaire **complet** : prix d'achat, ou enfants + main-d'œuvre pour un ensemble | Non — un parent contient déjà ses enfants |
| `rolled_up_contribution` | Ce que pèse **cette occurrence**, enfants inclus : quantité du chemin × `unit_cost` | Non, pas entre niveaux |
| `own_unit_cost` | Coût **propre** : le prix d'achat, ou la seule main-d'œuvre si la pièce est fabriquée | — |
| `own_contribution` | Quantité cumulée × `own_unit_cost` | **Oui** : sa somme sur toutes les pièces égale exactement le total |

Une ligne de l'arbre affiche `rolled_up_contribution` — c'est la question que l'utilisateur pose en
dépliant. La vue agrégée affiche `own_contribution` — c'est celle qui reconstitue le total. Les
additionner ensemble, c'est compter deux fois.

### 1.4 Pagination

Paramètres `limit` (défaut 50, maximum 500) et `offset`. Réponse :

```json
{ "items": [ ... ], "total": 137, "limit": 50, "offset": 0 }
```

### 1.5 Erreurs

```json
{ "error": { "code": "PARAMETER_NOT_APPLICABLE", "message": "…", "details": { "part_ref": "GMP-ASSY" } } }
```

| Code | HTTP | Quand |
|---|---|---|
| `BOM_VERSION_NOT_FOUND` | 404 | Version de nomenclature inconnue |
| `BOM_VERSION_NOT_VALIDATED` | 409 | La version n'a pas passé le contrôle d'intégrité : aucun calcul n'est autorisé dessus |
| `PATH_NOT_FOUND` | 404 | Le chemin ne correspond à aucune suite d'arêtes existante |
| `PART_NOT_FOUND` | 404 | Référence inconnue dans cette version |
| `SCENARIO_NOT_FOUND` | 404 | Identifiant de scénario inconnu |
| `PARAMETER_NOT_APPLICABLE` | 422 | Fournisseur, usine ou prix posé sur un nœud **fabriqué** ; temps de main-d'œuvre posé sur un nœud **acheté** (ADR-0008) |
| `PLANT_NOT_AVAILABLE_FOR_SUPPLIER` | 422 | L'usine demandée n'appartient pas au fournisseur retenu (ADR-0010) |
| `PRICE_OVERRIDE_JUSTIFICATION_REQUIRED` | 422 | Prix forcé sans justification |
| `SCOPE_PATH_REQUIRES_PATH` | 422 | `scope = "path"` sans chemin, ou `scope = "part"` avec chemin |
| `OCCURRENCE_VIEW_TOO_LARGE` | 422 | La vue par occurrence demandée dépasse la borne (voir §4.3) |
| `NO_PRICE_SNAPSHOT` | 409 | Aucun snapshot disponible, même périmé |
| `PRICE_SNAPSHOT_NOT_FOUND` | 404 | Identifiant de snapshot inconnu (journal de quarantaine, ou `price_snapshot_id` d'un calcul) |
| `CALCULATION_FAILED` | 500 | Échec interne ; le calcul est persisté avec `status = "FAILED"` |

**Une panne de l'API de prix ne produit jamais d'erreur HTTP** : elle produit un calcul de statut
`DEGRADED` ou `INCOMPLETE` (§6).

### 1.6 Traçabilité

Toute réponse de calcul porte : `bom_version`, `price_snapshot_id`, `rules_version`,
`engine_version`, `computed_at`, `display_currency`, `input_digest`.

---

## 2. Nomenclature — lecture du graphe

### 2.1 `GET /bom/versions`

```json
{ "items": [ { "id": "bom-multipla-2026-09-22", "label": "Fiat Multipla 1.6 16V",
  "root_part_ref": "VEH-MULTIPLA-16V", "part_count": 474, "edge_count": 689,
  "validated_at": "2026-09-22T10:04:11Z", "is_synthetic": true } ] }
```

`is_synthetic: true` est **toujours** renvoyé et affiché : les données sont plausibles mais inventées.

Une version pas encore validée est listée avec `validated_at: null` : l'écran peut dire pourquoi
elle ne s'ouvre pas. Une version validée ne change plus (ADR-0013).

### 2.2 `GET /bom/{bom_version}/root`

Renvoie la ligne racine, au même format qu'un enfant (§2.3), avec `path` de longueur 1.

### 2.3 `GET /bom/{bom_version}/children` — **le dépliage**

C'est la route centrale de l'écran. Elle renvoie **les enfants directs et rien d'autre**.

| Paramètre | Obligatoire | Rôle |
|---|---|---|
| `path` | oui | Le nœud à déplier |
| `calculation_id` | non | Enrichit chaque ligne des chiffres de ce calcul |
| `limit`, `offset` | non | Pagination des enfants |

```json
{
  "path": "VEH-MULTIPLA-16V/GMP-ASSY",
  "items": [
    {
      "path": "VEH-MULTIPLA-16V/GMP-ASSY/ENG-BLOCK-ASSY",
      "part_ref": "ENG-BLOCK-ASSY",
      "label": "Bloc-cylindres assemblé",
      "system": "GMP",
      "valuation_mode": "manufactured",
      "edge_quantity": "1.000000",
      "unit": "pce",
      "has_children": true,
      "child_count": 14,
      "parent_count": 1,
      "occurrence_count": 1,
      "is_modified": false,
      "has_modified_descendant": true,
      "unit_cost": { "amount": "412.550000", "currency": "EUR" },
      "rolled_up_contribution": { "amount": "412.550000", "currency": "EUR" },
      "own_contribution": { "amount": "29.400000", "currency": "EUR" },
      "rolled_up_co2": { "kg_co2e": "88.200000" },
      "price_status": "OK"
    },
    {
      "path": "VEH-MULTIPLA-16V/GMP-ASSY/FIX-M6-16",
      "part_ref": "FIX-M6-16",
      "label": "Vis M6×16",
      "system": "FIX",
      "valuation_mode": "purchased",
      "edge_quantity": "8.000000",
      "unit": "pce",
      "has_children": false,
      "child_count": 0,
      "parent_count": 10,
      "occurrence_count": 12,
      "is_modified": true,
      "has_modified_descendant": false,
      "unit_cost": { "amount": "0.042000", "currency": "EUR" },
      "rolled_up_contribution": { "amount": "0.336000", "currency": "EUR" },
      "own_contribution": { "amount": "0.336000", "currency": "EUR" },
      "rolled_up_co2": { "kg_co2e": "0.010400" },
      "price_status": "FALLBACK"
    }
  ],
  "total": 2, "limit": 50, "offset": 0
}
```

Points de contrat :

- **`parent_count`** = nombre de parents directs distincts. **`occurrence_count`** = nombre de
  chemins depuis la racine. Le badge « utilisée à N endroits » affiche **`occurrence_count`** ; les
  deux sont renvoyés parce qu'ils diffèrent dès qu'un sous-ensemble est lui-même monté plusieurs fois.
- `rolled_up_contribution` est ce que pèse **cette occurrence**, enfants inclus. Sur un nœud acheté,
  elle est égale à `own_contribution` : une feuille n'a rien en dessous d'elle.
- `has_modified_descendant` est calculé **côté serveur** : le front ne connaît pas le graphe et ne
  peut pas le déduire (ADR-0009).
- Sans `calculation_id`, les champs monétaires sont absents — jamais `null` déguisé en zéro.
- `price_status` dit d'où vient le prix **de cette ligne** : `OK` ; `FALLBACK` (absente de la
  réponse de l'API, dernier prix connu retenu) ; `QUARANTINED` (reçue mais refusée, dernier prix
  sain retenu — le détail est au journal, §5.3) ; `MISSING` (aucun prix, jamais un zéro). Une
  ligne n'a qu'un statut : refusée **et** sans historique, elle est `MISSING`. Un prix forcé par
  le scénario est `OK` : ce qui est arrivé au snapshot ne dit plus rien du montant affiché. Seule
  la ligne concernée est marquée ; ses parents ne le sont pas.

### 2.4 `GET /bom/{bom_version}/where-used`

```
?part_ref=FIX-M6-16&calculation_id=…&limit=50&offset=0
```

```json
{
  "part_ref": "FIX-M6-16",
  "occurrence_count": 12,
  "cumulative_quantity": "148.000000",
  "unit": "pce",
  "items": [
    { "path": "VEH-MULTIPLA-16V/GMP-ASSY/FIX-M6-16",
      "path_labels": ["Véhicule complet", "Groupe motopropulseur", "Vis M6×16"],
      "quantity_on_path": "8.000000",
      "own_contribution": { "amount": "0.336000", "currency": "EUR" } }
  ],
  "total": 12, "limit": 50, "offset": 0
}
```

### 2.5 `GET /bom/{bom_version}/search`

```
?q=vis m6&limit=20
```

Chaque résultat porte **ses chemins**, pour que le front puisse déplier de proche en proche jusqu'à
la pièce (ADR-0009) :

```json
{ "items": [ { "part_ref": "FIX-M6-16", "label": "Vis M6×16", "system": "FIX",
  "occurrence_count": 12, "paths": ["VEH-MULTIPLA-16V/GMP-ASSY/FIX-M6-16", "…"],
  "paths_truncated": true } ] }
```

### 2.6 `GET /bom/{bom_version}/parts/{part_ref}`

Fiche d'une pièce : champs du jeu de données, `cumulative_quantity`, `occurrence_count`, et — si elle
est `purchased` — la liste de ses fournisseurs et, pour chacun, ses usines :

```json
{
  "part_ref": "FIX-M6-16", "valuation_mode": "purchased", "unit": "pce",
  "carbon_factor": { "kg_co2e_per_unit": "0.001300" },
  "suppliers": [
    { "supplier_id": "SUP-BULLONI", "name": "Bulloni SpA", "price_multiplier": "1.080000",
      "comment": "transport_co2_kg_per_kg est une intensité : on la multiplie par la masse de la pièce",
      "plants": [
        { "plant_id": "PLT-BULLONI-IT", "origin": "IT", "price_coefficient": "1.000000",
          "lead_time_days": 12, "transport_co2_kg_per_kg": "0.021000", "is_default": true },
        { "plant_id": "PLT-BULLONI-TR", "origin": "TR", "price_coefficient": "0.920000",
          "lead_time_days": 34, "transport_co2_kg_per_kg": "0.142000", "is_default": false }
      ] }
  ]
}
```

Sur une pièce `manufactured`, la clé `suppliers` est **absente** — pas vide : le panneau de saisie ne
doit pas pouvoir proposer un fournisseur sur un ensemble (ADR-0008).

---

## 3. Scénarios

### 3.1 `POST /scenarios`

```json
{ "bom_version": "bom-multipla-2026-09-22", "name": "Sourcing Turquie",
  "display_currency": "EUR", "labour_rate": "42.000000",
  "active_rules": ["labour"],
  "parameters": [ { "part_ref": "FIX-M6-16", "scope": "part",
                    "supplier_id": "SUP-BULLONI", "plant_id": "PLT-BULLONI-TR",
                    "purchase_currency": "USD" } ] }
```

`parameters` est facultatif (liste vide par défaut). Le scénario et ses paramètres sont sauvegardés
dans une seule transaction. La réponse `201` contient le scénario relu, avec son nom et tous ses
réglages. Un nom vide est refusé. Les références sont vérifiées dans la nomenclature **validée** de
la version demandée, même sans snapshot de prix : une pièce inconnue provoque
`422 PARAMETER_NOT_APPLICABLE` avant toute écriture.

Les toggles sont représentés par `active_rules` : `[]` désactive la main-d'œuvre,
`["labour"]` l'active (ADR-0006). La provenance est le choix de `plant_id`, distinct du
fournisseur (ADR-0010). La devise d'achat est distincte de la devise d'affichage ; elle est
conservée ici. Un snapshot porte aujourd'hui une seule devise : la sélection d'un prix dans une
autre devise attend le catalogue multi-devise du périmètre prix, sans conversion à taux courant.

### 3.2 `GET /scenarios` — lister les scénarios

Renvoie tous les scénarios du plus récent au plus ancien. Chaque élément utilise le même format que
`GET /scenarios/{id}`, y compris les paramètres et l'état du calcul calculé côté serveur :

```json
{
  "items": [
    { "id": "scn-8f2…", "name": "Sourcing Turquie", "parameters": [] }
  ],
  "total": 1
}
```

Une base sans scénario renvoie `{"items": [], "total": 0}`.

### 3.3 `GET /scenarios/{id}`

Renvoie le scénario, ses paramètres, et **l'état du calcul**, qui est une donnée serveur (§6.2) :

```json
{ "id": "scn-8f2…", "name": "Sourcing Turquie",
  "bom_version": "bom-multipla-2026-09-22", "display_currency": "EUR",
  "labour_rate": "42.000000",
  "active_rules": ["labour"], "parameters": [ … ],
  "calculation_state": "PARAMETERS_CHANGED",
  "stale_reason": "parameters",
  "last_calculation_id": "calc-41b…" }
```

`last_calculation_id` désigne le dernier calcul enregistré (`null` s'il n'y en a aucun). L'écran le
relit avec `GET /calculations/{id}` pour réafficher un scénario rouvert, sans relancer de calcul.

Chaque paramètre expose `parameter_id`, `part_ref`, `scope`, `path`, `supplier_id`, `plant_id`,
`purchase_currency`, `price_override`, `price_override_justification` et `labour_minutes`.
`parameter_id` est l'identifiant `prm-…` à passer à la route de suppression ; il reste donc
récupérable après un redémarrage ou lorsque la réponse initiale du `PUT` n'a pas été conservée.
**`purchase_currency` est accepté et persisté, mais n'a aucun effet sur le calcul** : aucune
conversion de devise n'existe encore, les prix restent ceux du snapshot. Le champ entre seulement
dans l'empreinte des entrées, si bien qu'il marque les totaux obsolètes. Choix retenu en revue du
2026-09-30 : le laisser tel quel jusqu'à la tranche devises.
Les valeurs décimales sont des chaînes, sans arrondi. Un réglage qui dépasse l'échelle de stockage
(6 décimales pour les montants, 4 pour les minutes) est refusé plutôt qu'arrondi silencieusement.

### 3.4 `PUT /scenarios/{id}/parameters/{target}` — poser un paramètre

`target` est soit une référence (portée pièce), soit un chemin (portée chemin). La portée est
**explicite**, jamais déduite (ADR-0002).

`scope` omis vaut `part`. Pour `path`, `target` est le chemin complet depuis la racine,
avec ses `/` ; le serveur vérifie chaque arête et la référence finale. Si le corps comporte
également `path`, il doit correspondre à `target`. Une cible pièce ne peut pas porter de chemin.
Les deux portées peuvent coexister pour une même pièce ; une mise à jour ne remplace que la cible
exacte. La réponse de portée chemin indique `affects_occurrences = 1`.

```json
{ "scope": "part",
  "supplier_id": "SUP-BULLONI",
  "plant_id": "PLT-BULLONI-TR",
  "purchase_currency": "EUR",
  "price_override": null,
  "price_override_justification": null,
  "labour_minutes": null }
```

Réponse : le paramètre créé ou remplacé, **et la portée effective en clair**, que l'écran affiche
tel quel :

```json
{ "parameter_id": "prm-77c…", "scope": "part", "part_ref": "FIX-M6-16",
  "affects_occurrences": 12,
  "scope_label": "S'applique aux 12 occurrences de cette pièce",
  "calculation_state": "PARAMETERS_CHANGED" }
```

Règles de validation, refusées en 422 :

- fournisseur, usine, devise d'achat ou prix forcé sur un nœud `manufactured` ;
- temps de main-d'œuvre sur un nœud `purchased` ;
- usine n'appartenant pas au fournisseur retenu ;
- prix forcé sans justification non vide ;
- `scope = "path"` sans chemin, ou l'inverse.

**Précédence** : si une pièce porte à la fois un paramètre de portée pièce et un de portée chemin,
**le plus spécifique gagne**, et l'explication (§4.4) dit lequel s'est appliqué.

Le calcul applique cette précédence. La vue agrégée conserve une contribution exacte et expose un
coût unitaire moyen pondéré à l'échelle de stockage lorsque deux occurrences de la même pièce ont
des coûts différents.
La vue par chemin conserve le coût propre et le coût complet de l'occurrence surchargée ; ces coûts
de contexte sont persistés avec le calcul (`calculation_context_cost`, migration 0002), si bien que
l'arbre relu depuis la base affiche le coût de chaque occurrence et non la moyenne de la ligne.
Le paramètre de chemin remplace la cible complète : un champ omis y reprend la valeur par défaut du
catalogue, pas la valeur du paramètre de portée pièce.

### 3.5 `DELETE /scenarios/{id}/parameters/{parameter_id}`

Réponse `200` avec le nouvel `calculation_state`.

### 3.6 `DELETE /scenarios/{id}` — supprimer un scénario

Réponse `204` sans corps. La suppression est définitive : les paramètres, les calculs et les
résultats persistés de ce scénario sont supprimés en cascade. La nomenclature et les snapshots
de prix sont conservés, car ils peuvent être utilisés par d'autres scénarios. Un identifiant inconnu
provoque `404 SCENARIO_NOT_FOUND`.

### 3.7 `POST /scenarios/{id}/duplicate` — préparer un autre scénario

```json
{ "name": "Alternative Allemagne" }
```

Réponse `201` : le scénario copié, avec un nouvel `id` et le nom demandé. La version de BOM,
les devises, le taux horaire, les règles actives et tous les paramètres sont conservés.
Les paramètres de la copie ont leurs propres identifiants en base ; modifier ou supprimer un
réglage de la copie ne change pas l'original. Aucun calcul n'est copié ou lancé et aucune
comparaison n'est effectuée. Une source inconnue provoque `404 SCENARIO_NOT_FOUND`.

### 3.8 `POST /scenarios/compare` — comparer A et B

```json
{ "scenario_a_id": "scn-base", "scenario_b_id": "scn-variante",
  "price_snapshot_id": "snp-19a…" }
```

Les deux scénarios sont calculés par le moteur normal avec le même snapshot. Ils doivent partager
la version de nomenclature et la devise d'affichage. La réponse contient `total_a`, `total_b`,
`cost_delta` (`B - A`) et jusqu'à dix `top_differences`, triées par valeur absolue décroissante puis
par référence. Chaque différence porte les deux contributions et les quantités cumulées ; une
pièce partagée est donc pondérée par sa quantité totale, jamais par une seule occurrence.
Une comparaison est refusée avec `422 INCOMPARABLE_SCENARIOS` si l'un des calculs est incomplet :
une contribution sans prix ne doit jamais être assimilée à zéro.

`co2_delta_kg` vaut `null` tant que le calcul ne porte pas les projections carbone de NLPF-47/48.
Le champ est déjà stable et devient numérique dès que les deux calculs portent `total_co2`.

### 3.9 `POST /scenarios/{id}/recommend-sourcing` — recommandation contrainte

Décision : [ADR-0012](adr/0012-comparaison-et-recommandation-par-piece.md).

```json
{ "name": "Sourcing optimisé", "price_snapshot_id": "snp-19a…",
  "forbidden_origins": ["RU"], "max_lead_time_days": 30,
  "accepted_part_refs": ["FIX-M6-16", "TRN-BEARING-BALL"] }
```

Pour chaque pièce achetée sans prix forcé, le serveur évalue les couples fournisseur/usine connus,
écarte les provenances interdites et les délais trop longs, puis retient le prix unitaire minimal.
Les égalités sont départagées par identifiants fournisseur puis usine, afin de rendre le résultat
déterministe. La réponse explique le choix avec les options actuelle et recommandée, la provenance,
le délai, la quantité affectée et l'économie estimée.
Un calcul de base incomplet est refusé avec `409 INCOMPLETE_CALCULATION`, car aucune économie fiable
ne peut être calculée à partir d'un prix manquant.

Si l'option actuelle **viole une contrainte**, l'option autorisée la moins chère est proposée même
si elle coûte plus cher : la ligne porte `required_by_constraint: true` et une économie négative.
Si aucune option autorisée n'existe, la pièce figure dans **`unresolved`** avec son sourcing actuel
et une raison ; elle n'est jamais ignorée en silence, car la variante la garderait telle quelle.

`accepted_part_refs` permet de n'appliquer qu'une partie des recommandations. Omis, il accepte tout ;
vide, il crée une copie indépendante sans modification. La réponse `201` contient le scénario créé,
les recommandations marquées `accepted`, les `unresolved` et l'économie exacte issue d'une
comparaison des deux calculs sur le même snapshot.

### 3.10 `POST /scenarios/{id}/recommend-sourcing/preview` — aperçu sans création

Même corps que §3.9, sans `name` ni `accepted_part_refs`. Réponse `200` : `base_scenario_id`,
`price_snapshot_id` (celui réellement utilisé), `constraints`, `recommendations` et `unresolved`.
**Aucun scénario n'est créé** ; seul le calcul de base est enregistré. L'écran s'en sert pour faire
cocher les lignes, puis appelle §3.9 avec les lignes retenues et **le même `price_snapshot_id`**,
pour que l'économie annoncée porte sur les prix que l'utilisateur a vus.

---

## 4. Calcul

### 4.1 `POST /calculations`

```json
{ "scenario_id": "scn-8f2…", "price_snapshot_id": null }
```

`price_snapshot_id` omis ou `null` ⇒ le dernier snapshot disponible, même périmé. Réponse `201` :

```json
{
  "id": "calc-41b…",
  "status": "DEGRADED",
  "bom_version": "bom-multipla-2026-09-22",
  "price_snapshot": { "id": "snp-19a…", "taken_at": "2026-09-21T06:00:00Z",
    "age_seconds": 97200, "status": "STALE", "is_fallback": true },
  "rules_version": "rules-1", "engine_version": "engine-0.1.0",
  "computed_at": "2026-09-22T09:03:44Z",
  "input_digest": "sha256:7c1e…",
  "display_currency": "EUR",
  "total_cost": { "amount": "8431.902400", "currency": "EUR" },
  "total_co2": { "kg_co2e": "4120.550000" },
  "systems": [
    { "system": "GMP", "label": "Groupe motopropulseur",
      "cost": { "amount": "2914.220000", "currency": "EUR" }, "cost_share_pct": "34.6",
      "co2": { "kg_co2e": "1602.300000" }, "co2_share_pct": "38.9" }
  ],
  "top_cost_contributors": [
    { "part_ref": "ENG-BLOCK-RAW", "label": "Bloc-cylindres brut",
      "contribution": { "amount": "612.000000", "currency": "EUR" }, "share_pct": "7.3",
      "first_path": "VEH-MULTIPLA-16V/GMP-ASSY/ENG-BLOCK-ASSY/ENG-BLOCK-RAW" }
  ],
  "top_co2_contributors": [ … ],
  "issue_counts": { "missing_price": 0, "quarantined": 2, "fallback": 37 }
}
```

- La somme des `systems[].cost` est **exactement** `total_cost` (ADR-0011). Les pourcentages, eux,
  sont arrondis à une décimale et peuvent ne pas totaliser 100.
- `first_path` permet au front de déplier jusqu'au contributeur en un clic.
- `issue_counts` compte les **pièces** selon leur `price_status` (§2.3) : les trois catégories sont
  disjointes. Ce n'est pas le `counts` d'un snapshot (§5.1), où `fallback` inclut les valeurs mises
  en quarantaine puis remplacées.

### 4.2 `GET /calculations/{id}/aggregated` — vue agrégée

Une ligne par **pièce**.

```
?sort=contribution_desc&system=GMP&limit=50&offset=0
```

```json
{ "items": [ { "part_ref": "FIX-M6-16", "label": "Vis M6×16", "system": "FIX",
    "valuation_mode": "purchased",
    "cumulative_quantity": "148.000000", "unit": "pce",
    "unit_cost": { "amount": "0.042000", "currency": "EUR" },
    "own_unit_cost": { "amount": "0.042000", "currency": "EUR" },
    "own_contribution": { "amount": "6.216000", "currency": "EUR" },
    "own_co2_contribution": { "kg_co2e": "0.192400" },
    "occurrence_count": 12, "price_status": "FALLBACK" } ],
  "total": 372, "limit": 50, "offset": 0,
  "sum_of_own_contributions": { "amount": "8431.902400", "currency": "EUR" } }
```

`sum_of_own_contributions` porte sur **l'ensemble des pièces, pas sur la page courante** : c'est la
valeur que le test d'invariant compare au total. Elle est exactement égale à `total_cost`, et elle
est aussi égale au `unit_cost` de la racine — deux façons de dire la même chose, que le générateur
du jeu de données vérifie déjà sur les données réelles.

### 4.3 `GET /calculations/{id}/occurrences` — vue par occurrence

Une ligne par **chemin**. Exige `path` : cette vue est bornée à un sous-arbre et **n'est jamais
demandée pour le véhicule entier** (ADR-0005).

```
?path=VEH-MULTIPLA-16V/GMP-ASSY&limit=100&offset=0
```

Au-delà de 5 000 occurrences dans le sous-arbre demandé : `422 OCCURRENCE_VIEW_TOO_LARGE`, avec le
compte exact dans `details`, pour que l'utilisateur descende d'un cran.

### 4.4 `GET /calculations/{id}/explain` — d'où vient ce montant

```
?path=VEH-MULTIPLA-16V/GMP-ASSY/ENG-BLOCK-ASSY/ENG-OIL-PAN-ASSY/FIX-M6-16
```

```json
{
  "path": "VEH-MULTIPLA-16V/GMP-ASSY/ENG-BLOCK-ASSY/ENG-OIL-PAN-ASSY/FIX-M6-16",
  "part_ref": "FIX-M6-16", "valuation_mode": "purchased",
  "unit_cost_breakdown": {
    "kind": "catalogue",
    "reference_price": { "amount": "0.039000", "currency": "EUR" },
    "supplier": { "supplier_id": "SUP-FIXPRO", "name": "FixPro Verbindungstechnik", "multiplier": "1.061720" },
    "plant": { "plant_id": "PLT-FIXPRO-DE", "origin": "DE", "coefficient": "1.000000" },
    "formula": "0.039000 × 1.061720 × 1.000000",
    "unit_cost": { "amount": "0.041407", "currency": "EUR" },
    "reproduced": true
  },
  "quantity": { "on_path": "16.000000", "cumulative_in_vehicle": "68.000000", "unit": "pce" },
  "occurrence_count": 9,
  "applied_parameter": null,
  "parameters_changed_since_calculation": false,
  "applied_rules": ["labour"],
  "price_source": { "snapshot_id": "snp-fd6b…", "status": "OK",
    "as_of": "2026-09-28T05:44:48Z", "reason": null }
}
```

`unit_cost_breakdown.kind` dit laquelle des trois formes on lit :

| `kind` | Sur | Contenu |
|---|---|---|
| `catalogue` | pièce achetée, prix du snapshot | Les trois facteurs (ADR-0010), la formule, le prix unitaire **enregistré**, et `reproduced` |
| `override` | pièce achetée, prix forcé | Le prix et sa `justification` (`null` si le scénario a changé depuis : elle n'est pas conservée avec le calcul) |
| `assembly` | ensemble fabriqué | `children` (quantité, coût unitaire, contribution), `children_cost`, `labour` (`labour_minutes`, `labour_rate`, `amount`), `unit_cost` — **et aucun prix** |

`unit_cost_breakdown` vaut `null` sur une pièce sans prix : `price_source.status` vaut alors `MISSING`.

Ce qui s'écarte de la première version de ce contrat, et pourquoi :

- **`reproduced`** : le calcul ne stocke que le fournisseur et l'usine retenus. Les facteurs sont
  relus dans le snapshot et le sourcing de la version, figés (ADR-0003, ADR-0013), puis on vérifie
  qu'ils redonnent le prix enregistré. Le coefficient d'usine n'est pas versionné : s'il a changé,
  `reproduced` vaut `false` plutôt que d'afficher une formule dont le résultat n'est pas celui de la
  ligne.
- **`applied_parameter`** n'est donné que si le scénario n'a pas changé depuis le calcul ; sinon il
  vaut `null` et `parameters_changed_since_calculation` vaut `true`. Le paramètre actuel n'est pas
  forcément celui qui a servi. Il ne porte pas d'identifiant : le dépôt n'en expose pas.
- **`price_source.as_of`** vaut `null` sur un prix de repli ou en quarantaine : la seule date connue
  est celle du snapshot qui reprend le prix, pas celle du prix. Remonter la chaîne des replis reste
  à faire.
- Pas de `reference_unit` ni de division : le moteur ne lit pas `price_per`, le prix de référence
  est déjà unitaire.

### 4.5 `GET /calculations/{id}/issues`

Les pièces sans prix, les prix en quarantaine et les prix de repli, avec un chemin — c'est la
source du bandeau d'alerte et la liste cliquable exigée par le mode de panne P3. Triées du plus
grave au moins grave (`MISSING_PRICE`, `QUARANTINED`, `FALLBACK`), puis par référence. Paginée
(§1.4).

```json
{ "items": [ { "kind": "MISSING_PRICE", "part_ref": "FIX-M6-16", "label": "Vis M6×16",
    "system": "FIX", "path": "VEH-MULTIPLA-16V/GMP-ASSY/…/FIX-M6-16",
    "cumulative_quantity": "68.000000", "occurrence_count": 9 } ],
  "total": 1, "limit": 50, "offset": 0 }
```

`path` est **un** chemin parmi d'autres, pour déplier l'arbre jusqu'à la pièce ; le where-used
(§2.4) donne les autres.

---

## 5. Prix

### 5.1 `POST /price-snapshots` — prendre un snapshot

```json
{ "id": "snp-20b…", "taken_at": "2026-09-22T09:00:00Z", "status": "FRESH",
  "counts": { "from_api": 210, "fallback": 3, "quarantined": 2, "missing": 0 } }
```

### 5.2 `GET /price-snapshots` — retrouver les snapshots disponibles

Les snapshots sont triés du plus récent au plus ancien afin que le premier identifiant puisse être
repris dans un calcul ou une comparaison :

```json
{
  "items": [
    {
      "id": "snp-20b…",
      "taken_at": "2026-09-22T09:00:00+00:00",
      "source": "mock-price-api",
      "currency": "EUR",
      "status": "FRESH",
      "age_seconds": 120,
      "counts": { "prices": 302, "fallback": 0, "quarantined": 0, "missing": 0 }
    }
  ],
  "total": 1
}
```

`status` vaut `FRESH` pendant 24 heures, `STALE` au-delà, ou `DEGRADED` lorsqu'un prix vient d'un
repli ou manque. Un snapshot **n'est jamais modifié** (ADR-0003).

### 5.3 `GET /price-snapshots/{id}/quarantine`

```json
{ "snapshot_id": "snp-8c3…",
  "items": [ { "part_ref": "ALT-BEARING", "currency": "EUR",
  "rejected_value": "-42.000000", "reason": "prix négatif",
  "replacement": { "amount": "4.200000", "currency": "EUR" },
  "replacement_from_snapshot": "snp-2a2…", "detected_at": "2026-09-24T08:33:42.259757+00:00" } ] }
```

- Un snapshot sain a un journal **vide** (`items: []`) ; un identifiant inconnu est un
  `404 PRICE_SNAPSHOT_NOT_FOUND` — un journal vide ne doit pas pouvoir se lire comme « tout allait
  bien » pour un snapshot qui n'existe pas.
- `rejected_value` est la valeur **telle que reçue**, en texte : elle peut n'être pas un nombre.
- `replacement` est un **prix de référence** (ADR-0010), pas le coût unitaire de la ligne :
  multiplicateur fournisseur et coefficient d'usine s'appliquent ensuite. `null` si rien n'a pu
  être retenu — la pièce est alors sans prix.
- `reason` est **une phrase**, pas un code. Écart avec la version initiale de ce contrat, qui
  prévoyait `NEGATIVE_PRICE`, `ZERO_PRICE_ON_PURCHASED`, `NOT_A_NUMBER`, `UNKNOWN_CURRENCY`,
  `OUT_OF_CATALOG_RANGE`, `DEVIATION_ABOVE_THRESHOLD` : la prise de snapshot écrit en base le motif
  lisible (« prix négatif », « écart de 60 % au dernier prix connu (0.5) »), et c'est lui que
  l'écran affiche. Un code stable demanderait une colonne de plus — à ajouter si un consommateur
  doit trier ou filtrer par motif.

### 5.4 L'API de prix simulée (service externe, port distinct)

Ce n'est pas notre API : c'est le service qu'on interroge, et qu'on a écrit pour pouvoir le faire
tomber à la demande.

```
GET /prices?refs=FIX-M6-16,ELE-ECU-MAIN&currency=EUR
X-Mock-Failure: none | timeout | outlier | missing | partial
```

```json
{ "as_of": "2026-09-22T09:00:00Z",
  "prices": [ { "ref": "FIX-M6-16", "currency": "EUR", "price": 42.0, "per": 1000 } ] }
```

Le déclenchement de panne est un **en-tête**, pas un hasard : la démonstration doit être
reproductible.

---

## 6. États

### 6.1 Statut d'un calcul

| Statut | Sens | Ce que l'écran doit montrer |
|---|---|---|
| `OK` | Tous les prix viennent d'un snapshot sain | Rien de particulier |
| `DEGRADED` | Au moins un prix vient d'un repli, ou le snapshot est périmé | Marqueur sur le total **et** sur les lignes concernées |
| `INCOMPLETE` | Au moins une pièce achetée n'a aucun prix connu | Total explicitement partiel, liste des pièces manquantes |
| `FAILED` | Échec interne | Message d'échec ; aucun total affiché |

`INCOMPLETE` n'est **jamais** réparé par un zéro (mode de panne P3).

### 6.2 État du calcul, du point de vue de l'écran

Renvoyé par `GET /scenarios/{id}` et recalculé côté serveur en comparant l'empreinte des entrées
courantes à `input_digest` du dernier calcul :

| Valeur | Sens |
|---|---|
| `NEVER_RUN` | Aucun calcul sur ce scénario |
| `UP_TO_DATE` | Le dernier calcul correspond aux paramètres actuels |
| `PARAMETERS_CHANGED` | Des paramètres ont changé depuis : **les totaux affichés sont obsolètes** |
| `RUNNING` | Calcul en cours |
| `FAILED` | Dernier calcul en échec |

C'est une donnée serveur, pas une déduction du front : le navigateur ne connaît pas le graphe et ne
peut pas savoir ce qu'un paramètre a touché.

En v1, le calcul est **synchrone** : `POST /calculations` ne rend la main qu'une fois le calcul
terminé, et la ligne n'est écrite en base qu'à la fin. `RUNNING` est donc l'état d'attente du client
pendant que la requête est en vol ; le serveur ne le renvoie jamais. Il figure ici parce qu'un calcul
asynchrone le rendrait observable, et que l'écran doit déjà savoir l'afficher.

---

## 7. Couverture des critères d'acceptation de l'écran

| Critère | Route |
|---|---|
| Naviguer de la racine jusqu'à une vis | `GET /bom/{v}/root` puis `GET /bom/{v}/children` |
| Déplier ne charge que les enfants directs | `GET /bom/{v}/children` (aucune profondeur en paramètre) |
| Badge « utilisée à N endroits » + where-used | `occurrence_count` puis `GET /bom/{v}/where-used` |
| Panneau différent achat / fabrication | `GET /bom/{v}/parts/{ref}` : `suppliers` absent si `manufactured` |
| Portée du réglage visible | `scope_label` et `affects_occurrences` dans la réponse de `PUT …/parameters/{target}` |
| Nœud modifié et remontée marqués | `is_modified` et `has_modified_descendant` sur chaque ligne d'enfant |
| Totaux marqués obsolètes | `calculation_state = PARAMETERS_CHANGED` |
| Total affiché = total de l'API, au centime | `total_cost` ; le front formate, il ne calcule pas |
| Décomposition par système = total | `systems[]`, dont la somme est exactement `total_cost` |
| Âge du snapshot visible en permanence | `price_snapshot.age_seconds` et `status` sur chaque calcul |
| Recherche qui déplie jusqu'à la pièce | `GET /bom/{v}/search` renvoyant les chemins |

---

## 8. Ce que l'API ne fait pas

- Elle n'expose aucune écriture sur la nomenclature : la BOM vient du seed (périmètre §2.4).
- Elle ne renvoie jamais le graphe entier en une réponse.
- Elle ne renvoie aucun montant en nombre flottant.
- Elle ne calcule pas encore la projection carbone : ce moteur appartient à NLPF-47/48.
- Elle ne convertit pas une devise à l'exécution ; les taux courants rendraient le calcul
  irreproductible.
