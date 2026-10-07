# Schéma de la base — 3istor

Le schéma PostgreSQL tel que le produisent les migrations `0001` à `0007`
([backend/migrations/](../backend/migrations/)). La source de vérité reste le SQL : si ce document et une
migration divergent, c'est la migration qui a raison, et ce document qu'il faut corriger.

Trois diagrammes, un par zone, plutôt qu'un seul illisible. Les tables qui reviennent d'un diagramme à
l'autre (`bom_version`, `supplier`, `price_snapshot`…) n'y portent que leur clé.

Conventions : `PK` clé primaire, `FK` clé étrangère, `UK` unicité. Les montants sont en
`numeric(18, 6)`, sans arrondi en base (ADR-0011).

---

## 1. Nomenclature et sourcing

Le graphe est une **table d'arêtes** (ADR-0001) : une pièce = une ligne, quel que soit le nombre de ses
parents. Les nomenclatures (Multipla, trois Valhalla) cohabitent, distinguées par `bom_version_id`.

```mermaid
erDiagram
    bom_version ||--o{ part : "contient"
    bom_version ||--o| bom_model : "porte (0008)"
    bom_version |o--o{ bom_version : "variante de (0008)"
    part ||--o{ bom_edge : "parent (fabriquée seulement)"
    part ||--o{ bom_edge : "enfant"
    part ||--o{ part_supplier : "achetée seulement"
    supplier ||--o{ part_supplier : "vend"
    supplier ||--o{ supplier_plant : "possède"

    bom_version {
        text id PK
        text label
        text root_part_ref
        text generator_version
        text seed_checksum "preuve du déterminisme"
        boolean is_synthetic
        int part_count
        int edge_count
        numeric reference_labour_rate "taux horaire de référence (0006)"
        timestamptz created_at
        timestamptz validated_at "NULL = aucun calcul permis"
        jsonb validation_report
        text parent_version_id FK "version dont dérive une variante (0008)"
    }
    bom_model {
        text bom_version_id PK,FK
        bytea glb "modèle 3D, écrit une fois"
        text sha256 "somme de contrôle du contenu"
        text source "generated | imported"
        timestamptz created_at
    }
    part {
        text bom_version_id PK,FK
        text part_ref PK
        text label
        text category
        text system
        text unit
        enum valuation_mode UK "purchased | manufactured"
        numeric labour_minutes "fabriquée seulement"
        numeric base_price_eur "achetée seulement"
        numeric price_per
        text material_ref
        numeric mass_kg
        numeric density_kg_m3 "densité synthétique, nullable (0008)"
        numeric carbon_factor_kg_co2e_per_unit
        numeric expected_cumulative_quantity "valeur de contrôle, lue par les tests"
    }
    bom_edge {
        text bom_version_id PK,FK
        text parent_ref PK,FK
        text child_ref PK,FK
        enum parent_valuation_mode FK "toujours manufactured"
        numeric quantity "quantité unitaire, > 0"
        numeric after_sales_quantity "SAV (0006)"
        text unit
    }
    supplier {
        text id PK
        text name
        text home_country
    }
    supplier_plant {
        text id PK
        text supplier_id FK,UK
        text label
        text origin_country
        numeric price_coefficient "coefficient d'usine"
        int lead_time_days "délai, en jours"
        numeric transport_co2_kg_per_kg
        boolean is_default
    }
    part_supplier {
        text bom_version_id PK,FK
        text part_ref PK,FK
        enum part_valuation_mode FK "toujours purchased"
        text supplier_id PK,FK
        numeric price_multiplier "multiplicateur fournisseur"
        boolean is_default "un seul par pièce"
    }
```

**Ce que la base garantit ici**

- **Valorisation exclusive** (ADR-0008) : quatre `CHECK` sur `part` (achetée ⇒ prix et pas de temps ;
  fabriquée ⇒ temps et pas de prix). La colonne `parent_valuation_mode` de `bom_edge`, fixée à
  `manufactured` et reliée à `part` par une clé composite `(bom_version_id, part_ref, valuation_mode)`,
  interdit à une pièce achetée d'avoir des enfants. `part_supplier` utilise le même mécanisme pour
  interdire un fournisseur sur un ensemble fabriqué.
- **Arêtes** : une seule arête par paire (parent, enfant), pas de boucle sur soi-même, quantité > 0.
- **Version validée figée** (ADR-0013, migration 0003) : dès que `validated_at` est renseigné, des
  déclencheurs refusent toute écriture sur `part`, `bom_edge`, `part_supplier` et `bom_version`.
- **Modèle 3D** (ADR-0017, migration 0008) : `bom_model` porte au plus un modèle par version ; il
  s'écrit une fois (`forbid_mutation` : ni `UPDATE`, ni `DELETE`) et se rattache même à une version
  validée, car il ne touche ni `part`, ni `bom_edge`, ni `part_supplier`. La base vérifie que
  `sha256` est celui du contenu (intégrité, pas une règle métier) et que `source` vaut `generated`
  ou `imported`. `part.density_kg_m3` est nullable et strictement positive ; `parent_version_id` doit
  désigner une version existante, autre que la version elle-même. Les densités sont synthétiques et
  la migration n'en remplit aucune.
- **Ce qu'elle ne garantit pas** : l'acyclicité, l'absence d'orphelin et l'unicité de la racine. Le
  chargeur les vérifie par tri topologique avant de renseigner `validated_at`.

Index utiles : `bom_edge (bom_version_id, child_ref)` pour le where-used ; trigramme sur `part.label`
pour la recherche.

---

## 2. Prix

Un snapshot de prix est une photographie **immuable** des prix d'une nomenclature (ADR-0003, ADR-0015).

```mermaid
erDiagram
    bom_version |o--o{ price_snapshot : "prix de"
    price_snapshot ||--o{ price_snapshot_line : "contient"
    price_snapshot |o--o{ price_snapshot_line : "repli depuis"
    price_snapshot ||--o{ price_quarantine : "journalise"
    price_snapshot |o--o{ price_quarantine : "remplacement depuis"

    bom_version {
        text id PK
    }
    price_snapshot {
        text id PK
        text bom_version_id FK "NULL pour les snapshots antérieurs à 0006"
        timestamptz taken_at
        text source
        enum status "FRESH | STALE | DEGRADED"
        jsonb counts "from_api, fallback, quarantined, missing"
        text degraded_reason "obligatoire si DEGRADED"
    }
    price_snapshot_line {
        text snapshot_id PK,FK
        text part_ref PK
        text currency PK
        numeric price
        numeric price_per
        enum origin "API | FALLBACK"
        timestamptz as_of
        text fallback_from_snapshot_id FK "obligatoire si FALLBACK"
    }
    price_quarantine {
        bigserial id PK
        text snapshot_id FK
        text part_ref
        text currency "texte : la valeur reçue peut être invalide"
        text rejected_value "texte : peut ne pas être un nombre"
        text reason
        numeric replacement_price
        text replacement_from_snapshot_id FK
        timestamptz detected_at
    }
```

- `price_snapshot` et `price_snapshot_line` : déclencheurs `forbid_mutation`, donc **ni UPDATE ni
  DELETE**.
- `price_snapshot_line.part_ref` ne porte **pas** de clé étrangère vers `part` : le lien passe par
  `price_snapshot.bom_version_id`.
- Les calculs « prix en direct » utilisent un snapshot transitoire **jamais écrit** dans ces tables.

---

## 3. Scénarios, calculs et snapshots de calcul

```mermaid
erDiagram
    bom_version ||--o{ scenario : "étudiée par"
    scenario ||--o{ scenario_parameter : "règle"
    supplier |o--o{ scenario_parameter : "fournisseur choisi"
    supplier_plant |o--o{ scenario_parameter : "usine choisie"

    scenario ||--o{ calculation : "produit"
    bom_version ||--o{ calculation : "sur"
    price_snapshot |o--o{ calculation : "aux prix de"
    calculation ||--o{ calculation_line : "une ligne par pièce"
    calculation ||--o{ calculation_system_total : "par système"
    calculation ||--o{ calculation_issue : "anomalies"
    calculation ||--o{ calculation_context_cost : "coûts par contexte"

    calculation ||--o| calculation_snapshot : "figé en"
    scenario ||--o{ calculation_snapshot : "gelé en"
    price_snapshot ||--o{ calculation_snapshot : "aux prix de"
    bom_version ||--o{ calculation_snapshot : "sur"
    calculation_snapshot ||--o{ calculation_snapshot_parameter : "copie"
    calculation_snapshot ||--o{ calculation_snapshot_name : "historique des noms"
    calculation_snapshot |o--o{ scenario : "derived_from"
    calculation_snapshot |o--o{ calculation_snapshot : "derived_from"

    scenario {
        text id PK
        text bom_version_id FK
        text name
        text display_currency
        numeric labour_rate "taux par défaut"
        text labour_rate_currency
        text_array active_rules "défaut : labour"
        boolean include_after_sales "SAV (0006)"
        text derived_from FK "snapshot de calcul d'origine (0005)"
        timestamptz created_at
        timestamptz updated_at
    }
    scenario_parameter {
        text id PK "prm-..."
        text scenario_id FK
        enum scope "part | path"
        text part_ref
        text path "obligatoire si path, finit par part_ref"
        text supplier_id FK
        text plant_id FK "doit appartenir au fournisseur"
        text purchase_currency
        numeric price_override
        text price_override_justification "obligatoire si prix forcé"
        numeric labour_minutes
        numeric labour_rate "taux propre à la cible (0007)"
        timestamptz created_at
    }
    calculation {
        text id PK
        text scenario_id FK
        text bom_version_id FK
        text price_snapshot_id FK
        text rules_version
        text engine_version
        text_array active_rules
        enum status "OK | DEGRADED | INCOMPLETE | FAILED"
        text display_currency
        numeric total_cost "obligatoire sauf FAILED"
        numeric total_co2
        text input_digest "empreinte des entrées"
        timestamptz started_at
        timestamptz finished_at
    }
    calculation_line {
        text calculation_id PK,FK
        text part_ref PK
        numeric cumulative_quantity
        text unit
        numeric unit_cost "complet, ne se somme pas"
        numeric own_unit_cost
        numeric own_contribution "se somme au total"
        numeric own_co2_contribution
        int occurrence_count
        text price_status
        text supplier_id FK
        text plant_id FK
    }
    calculation_system_total {
        text calculation_id PK,FK
        text system PK
        numeric cost
        numeric co2
        numeric cost_share_pct
        numeric co2_share_pct
    }
    calculation_issue {
        bigserial id PK
        text calculation_id FK
        enum kind "MISSING_PRICE | QUARANTINED | FALLBACK"
        text part_ref
        text detail
    }
    calculation_context_cost {
        text calculation_id PK,FK
        text scope PK "part | path"
        text target PK
        numeric own_unit_cost
        numeric full_unit_cost
    }
    calculation_snapshot {
        text id PK
        text name
        text name_key UK "fold(name), unique par BOM"
        text bom_version_id FK,UK
        text scenario_id FK
        text calculation_id FK,UK "un calcul ne se fige qu'une fois"
        text price_snapshot_id FK
        text scenario_name "copie"
        text display_currency "copie"
        numeric labour_rate "copie"
        text_array active_rules "copie"
        boolean include_after_sales "copie"
        text derived_from FK
        timestamptz created_at
    }
    calculation_snapshot_parameter {
        text snapshot_id FK
        enum scope
        text part_ref
        text path
        text supplier_id FK
        text plant_id FK
        text purchase_currency
        numeric price_override
        text price_override_justification
        numeric labour_minutes
        numeric labour_rate
    }
    calculation_snapshot_name {
        bigint seq PK
        text snapshot_id FK
        text name
        timestamptz renamed_at
    }
```

**Ce que la base garantit ici**

- **Un paramètre par cible** : index unique `(scenario_id, part_ref, coalesce(path, ''))`. Une pièce peut
  donc avoir un paramètre de portée `part` **et** des paramètres de portée `path`.
- **Usine cohérente avec le fournisseur** (ADR-0010) : clé composite `(plant_id, supplier_id)` vers
  `supplier_plant (id, supplier_id)`.
- **Prix forcé justifié** : `CHECK` sur la justification non vide.
- **Calcul non modifiable** (I5) : un déclencheur refuse tout `UPDATE`. La suppression reste possible, pour
  que supprimer un scénario supprime en cascade ses paramètres et ses calculs.
- **Snapshot de calcul** (ADR-0014) : seul le nom peut changer (déclencheur qui compare la ligne entière
  sans `name` et `name_key`) ; suppression interdite ; copie des paramètres et historique des noms en
  ajout seul. Aucune de ses clés étrangères n'est en cascade : un scénario qui porte un snapshot de calcul
  ne peut pas être supprimé (`409 SCENARIO_HAS_SNAPSHOTS`).
- `scenario_parameter.part_ref`, `calculation_line.part_ref` et `calculation_issue.part_ref` ne portent
  **pas** de clé étrangère vers `part` : la cohérence avec la nomenclature est contrôlée par
  l'application (`PARAMETER_NOT_APPLICABLE`).

---

## 4. Récapitulatif de l'immuabilité

| Table | INSERT | UPDATE | DELETE | Mécanisme |
|---|---|---|---|---|
| `part`, `bom_edge`, `part_supplier` | refusé si BOM validée | refusé si BOM validée | refusé si BOM validée | `forbid_change_to_validated_bom` (0003) |
| `bom_version` | oui | refusé si validée | refusé si validée | `forbid_change_to_validated_bom_version` (0003) |
| `bom_model` | oui (même sur version validée) | **non** | **non** | `forbid_mutation` (0008) |
| `price_snapshot`, `price_snapshot_line` | oui | **non** | **non** | `forbid_mutation` (0001) |
| `calculation` | oui | **non** | oui (cascade du scénario) | `forbid_mutation` (0001) |
| `calculation_snapshot` | oui | nom seul | **non** | 0004 |
| `calculation_snapshot_parameter`, `calculation_snapshot_name` | oui | **non** | **non** | `forbid_mutation` (0004) |

Le script [checks/contraintes.sql](../backend/migrations/checks/contraintes.sql) tente les 32 écritures
interdites et vérifie qu'elles sont toutes refusées ; la CI échoue si ce nombre change.

## 5. Types et domaines

| Nom | Définition |
|---|---|
| `valuation_mode` | `purchased`, `manufactured` |
| `parameter_scope` | `part`, `path` |
| `price_snapshot_status` | `FRESH`, `STALE`, `DEGRADED` |
| `price_line_origin` | `API`, `FALLBACK` |
| `calculation_status` | `OK`, `DEGRADED`, `INCOMPLETE`, `FAILED` |
| `calculation_issue_kind` | `MISSING_PRICE`, `QUARANTINED`, `FALLBACK` |
| `money_amount`, `quantity_value`, `co2_kg` | `numeric(18, 6)` |
| `coefficient` | `numeric(12, 6)` |
| `part_reference` | texte `^[A-Z0-9-]+$` (transportable dans une URL sans échappement) |
| `currency_code` / `country_code` | trois / deux lettres majuscules |

La table technique `schema_migration` enregistre les migrations appliquées.
