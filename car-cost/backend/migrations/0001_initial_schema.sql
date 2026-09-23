-- =============================================================================
-- 0001_initial_schema.sql — schéma initial de 3istor
--
-- Chaque contrainte de ce fichier porte la référence de la décision ou de
-- l'invariant qu'elle fait respecter. Une contrainte sans justification n'a
-- rien à faire ici.
--
--   I2 / ADR-0008  Valorisation exclusive : achetée (feuille, avec prix)
--                  xor fabriquée (enfants, sans prix)
--   I3             Structure : racine unique, pas d'arête en double, acyclicité
--   I5 / ADR-0003  Snapshots et calculs immuables
--   ADR-0010       Prix = référence x multiplicateur fournisseur x coef. usine
--   ADR-0011       Décimal exact, échelle 6 ; aucun arrondi en base
--
-- Ce que le schéma NE peut PAS garantir, et qui est donc vérifié au chargement :
--   - l'acyclicité du graphe (aucune contrainte déclarative ne l'exprime) ;
--   - l'absence de nœud orphelin ;
--   - l'unicité de la racine.
-- Le chargeur effectue ces trois contrôles par tri topologique et renseigne
-- bom_version.validated_at. Un calcul sur une version non validée est refusé
-- par l'application (BOM_VERSION_NOT_VALIDATED).
-- =============================================================================

BEGIN;

CREATE EXTENSION IF NOT EXISTS pg_trgm;  -- recherche par libellé (api.md §2.5)

CREATE TABLE schema_migration (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);

-- -----------------------------------------------------------------------------
-- Types
-- -----------------------------------------------------------------------------

CREATE TYPE valuation_mode         AS ENUM ('purchased', 'manufactured');
CREATE TYPE parameter_scope        AS ENUM ('part', 'path');
CREATE TYPE price_snapshot_status  AS ENUM ('FRESH', 'STALE', 'DEGRADED');
CREATE TYPE price_line_origin      AS ENUM ('API', 'FALLBACK');
CREATE TYPE calculation_status     AS ENUM ('OK', 'DEGRADED', 'INCOMPLETE', 'FAILED');
CREATE TYPE calculation_issue_kind AS ENUM ('MISSING_PRICE', 'QUARANTINED', 'FALLBACK');

-- ADR-0011 : échelle 6 partout, aucun arrondi en base.
CREATE DOMAIN money_amount   AS numeric(18, 6);
CREATE DOMAIN quantity_value AS numeric(18, 6);
CREATE DOMAIN coefficient    AS numeric(12, 6);
CREATE DOMAIN co2_kg         AS numeric(18, 6);

-- Une référence est en [A-Z0-9-]+ : c'est ce qui rend un chemin transportable
-- dans une URL sans échappement (api.md §1.1).
CREATE DOMAIN part_reference  AS text CHECK (VALUE ~ '^[A-Z0-9-]+$');
CREATE DOMAIN currency_code   AS text CHECK (VALUE ~ '^[A-Z]{3}$');
CREATE DOMAIN country_code    AS text CHECK (VALUE ~ '^[A-Z]{2}$');

-- -----------------------------------------------------------------------------
-- Interdiction de modification a posteriori (I5 / ADR-0003)
-- -----------------------------------------------------------------------------

CREATE FUNCTION forbid_mutation() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION '% est en écriture seule (ADR-0003) : opération % refusée',
        TG_TABLE_NAME, TG_OP
        USING ERRCODE = 'insufficient_privilege';
END;
$$;

-- =============================================================================
-- 1. Nomenclature
-- =============================================================================

CREATE TABLE bom_version (
    id                 text PRIMARY KEY,
    label              text NOT NULL,
    root_part_ref      part_reference NOT NULL,
    generator_version  text NOT NULL,
    seed_checksum      text NOT NULL,          -- preuve du déterminisme du générateur
    is_synthetic       boolean NOT NULL DEFAULT true,
    part_count         integer NOT NULL CHECK (part_count > 0),
    edge_count         integer NOT NULL CHECK (edge_count > 0),
    created_at         timestamptz NOT NULL DEFAULT now(),
    validated_at       timestamptz,            -- NULL tant que le tri topologique n'a pas été passé
    validation_report  jsonb
);

COMMENT ON COLUMN bom_version.is_synthetic IS
    'Les prix, masses et facteurs carbone sont plausibles mais inventés. '
    'Cette colonne est renvoyée par l''API et affichée : on ne présente pas des '
    'données synthétiques comme des données constructeur.';

COMMENT ON COLUMN bom_version.validated_at IS
    'Renseigné par le chargeur après contrôle : acyclicité par tri topologique, '
    'racine unique, aucun orphelin, aucune arête en double. Tant qu''il est NULL, '
    'aucun calcul n''est autorisé sur cette version.';

CREATE TABLE part (
    bom_version_id                  text NOT NULL REFERENCES bom_version (id) ON DELETE CASCADE,
    part_ref                        part_reference NOT NULL,
    label                           text NOT NULL,
    category                        text NOT NULL,
    system                          text NOT NULL,
    unit                            text NOT NULL,
    valuation_mode                  valuation_mode NOT NULL,
    labour_minutes                  numeric(12, 4),
    base_price_eur                  money_amount,
    price_per                       quantity_value NOT NULL DEFAULT 1 CHECK (price_per > 0),
    material_ref                    part_reference,
    mass_kg                         numeric(18, 6),
    carbon_factor_kg_co2e_per_unit  co2_kg NOT NULL CHECK (carbon_factor_kg_co2e_per_unit >= 0),
    expected_cumulative_quantity    quantity_value NOT NULL,

    PRIMARY KEY (bom_version_id, part_ref),

    -- I2 / ADR-0008 : les quatre faces de la valorisation exclusive.
    CONSTRAINT part_purchased_has_price
        CHECK (valuation_mode <> 'purchased' OR base_price_eur IS NOT NULL),
    CONSTRAINT part_manufactured_has_no_price
        CHECK (valuation_mode <> 'manufactured' OR base_price_eur IS NULL),
    CONSTRAINT part_purchased_has_no_labour
        CHECK (valuation_mode <> 'purchased' OR labour_minutes IS NULL),
    CONSTRAINT part_manufactured_has_labour
        CHECK (valuation_mode <> 'manufactured' OR labour_minutes IS NOT NULL),

    -- Cible des clés étrangères composites qui portent le mode de valorisation.
    CONSTRAINT part_ref_mode_uq UNIQUE (bom_version_id, part_ref, valuation_mode)
);

COMMENT ON COLUMN part.expected_cumulative_quantity IS
    'Valeur de contrôle issue du jeu de données : ce que le moteur DOIT trouver. '
    'Jamais lue par le moteur — uniquement par les tests.';

CREATE INDEX part_label_trgm_idx  ON part USING gin (label gin_trgm_ops);
CREATE INDEX part_system_idx      ON part (bom_version_id, system);

CREATE TABLE bom_edge (
    bom_version_id         text NOT NULL,
    parent_ref             part_reference NOT NULL,
    child_ref              part_reference NOT NULL,
    parent_valuation_mode  valuation_mode NOT NULL,
    quantity               quantity_value NOT NULL CHECK (quantity > 0),
    unit                   text NOT NULL,

    -- I3 : une paire (parent, enfant) est unique — aucune arête en double.
    PRIMARY KEY (bom_version_id, parent_ref, child_ref),

    CONSTRAINT edge_no_self_loop CHECK (parent_ref <> child_ref),

    -- I2 / ADR-0008 : seule une pièce FABRIQUÉE peut avoir des enfants.
    -- Garanti sans déclencheur : la clé étrangère composite ci-dessous ne peut
    -- pointer que sur une ligne de `part` dont le mode vaut 'manufactured',
    -- puisque la colonne est contrainte à cette seule valeur.
    CONSTRAINT edge_parent_is_manufactured CHECK (parent_valuation_mode = 'manufactured'),
    FOREIGN KEY (bom_version_id, parent_ref, parent_valuation_mode)
        REFERENCES part (bom_version_id, part_ref, valuation_mode)
        ON UPDATE CASCADE ON DELETE CASCADE,

    FOREIGN KEY (bom_version_id, child_ref)
        REFERENCES part (bom_version_id, part_ref) ON DELETE CASCADE
);

-- Dépliage d'un nœud : couvert par la clé primaire.
-- Where-used (remonter les parents d'une pièce) : index dédié.
CREATE INDEX bom_edge_child_idx ON bom_edge (bom_version_id, child_ref);

-- =============================================================================
-- 2. Sourcing — fournisseurs et usines (ADR-0010)
--
-- `transport_co2_kg_per_kg` est une INTENSITÉ : kg de CO2e par kilogramme de
-- pièce acheminée jusqu'au site d'assemblage. Le CO2 de transport d'un
-- bloc-cylindres n'est pas celui d'une vis ; un forfait par unité serait faux.
-- =============================================================================

CREATE TABLE supplier (
    id            text PRIMARY KEY,
    name          text NOT NULL,
    home_country  country_code NOT NULL
);

CREATE TABLE supplier_plant (
    id                         text PRIMARY KEY,
    supplier_id                text NOT NULL REFERENCES supplier (id) ON DELETE CASCADE,
    label                      text NOT NULL,
    origin_country             country_code NOT NULL,
    price_coefficient          coefficient NOT NULL CHECK (price_coefficient > 0),
    lead_time_days             integer NOT NULL CHECK (lead_time_days >= 0),
    transport_co2_kg_per_kg    co2_kg NOT NULL CHECK (transport_co2_kg_per_kg >= 0),
    is_default                 boolean NOT NULL DEFAULT false,

    -- Cible de la clé étrangère composite de scenario_parameter : une usine ne
    -- peut être choisie que chez le fournisseur qui la possède (ADR-0010).
    CONSTRAINT supplier_plant_id_supplier_uq UNIQUE (id, supplier_id)
);

CREATE TABLE part_supplier (
    bom_version_id       text NOT NULL,
    part_ref             part_reference NOT NULL,
    part_valuation_mode  valuation_mode NOT NULL,
    supplier_id          text NOT NULL REFERENCES supplier (id) ON DELETE CASCADE,
    price_multiplier     coefficient NOT NULL CHECK (price_multiplier > 0),
    is_default           boolean NOT NULL DEFAULT false,

    PRIMARY KEY (bom_version_id, part_ref, supplier_id),

    -- ADR-0008 : un ensemble fabriqué n'a pas de fournisseur. Même mécanisme
    -- déclaratif que pour les arêtes.
    CONSTRAINT part_supplier_only_on_purchased CHECK (part_valuation_mode = 'purchased'),
    FOREIGN KEY (bom_version_id, part_ref, part_valuation_mode)
        REFERENCES part (bom_version_id, part_ref, valuation_mode)
        ON UPDATE CASCADE ON DELETE CASCADE
);

CREATE UNIQUE INDEX part_supplier_single_default_idx
    ON part_supplier (bom_version_id, part_ref) WHERE is_default;

-- =============================================================================
-- 3. Prix — snapshots immuables (ADR-0003)
-- =============================================================================

CREATE TABLE price_snapshot (
    id               text PRIMARY KEY,
    taken_at         timestamptz NOT NULL,
    source           text NOT NULL,
    status           price_snapshot_status NOT NULL,
    counts           jsonb NOT NULL,   -- {from_api, fallback, quarantined, missing}
    degraded_reason  text,

    CONSTRAINT snapshot_degraded_has_reason
        CHECK (status <> 'DEGRADED' OR degraded_reason IS NOT NULL)
);

CREATE TABLE price_snapshot_line (
    snapshot_id                text NOT NULL REFERENCES price_snapshot (id),
    part_ref                   part_reference NOT NULL,
    currency                   currency_code NOT NULL,
    price                      money_amount NOT NULL CHECK (price >= 0),
    price_per                  quantity_value NOT NULL DEFAULT 1 CHECK (price_per > 0),
    origin                     price_line_origin NOT NULL,
    as_of                      timestamptz NOT NULL,
    fallback_from_snapshot_id  text REFERENCES price_snapshot (id),

    PRIMARY KEY (snapshot_id, part_ref, currency),

    -- P1/P2 : un prix de repli dit toujours d'où il vient.
    CONSTRAINT fallback_has_source
        CHECK (origin <> 'FALLBACK' OR fallback_from_snapshot_id IS NOT NULL)
);

CREATE TABLE price_quarantine (
    id                             bigserial PRIMARY KEY,
    snapshot_id                    text NOT NULL REFERENCES price_snapshot (id),
    part_ref                       part_reference NOT NULL,
    currency                       text NOT NULL,   -- texte : la devise reçue peut être invalide
    rejected_value                 text NOT NULL,   -- texte : la valeur reçue peut n'être pas un nombre
    reason                         text NOT NULL,
    replacement_price              money_amount,
    replacement_from_snapshot_id   text REFERENCES price_snapshot (id),
    detected_at                    timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX price_quarantine_snapshot_idx ON price_quarantine (snapshot_id);

-- Un snapshot n'est ni modifié, ni réparé, ni complété, ni supprimé.
CREATE TRIGGER price_snapshot_immutable
    BEFORE UPDATE OR DELETE ON price_snapshot
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE TRIGGER price_snapshot_line_immutable
    BEFORE UPDATE OR DELETE ON price_snapshot_line
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- =============================================================================
-- 4. Scénarios (ADR-0002)
-- =============================================================================

CREATE TABLE scenario (
    id                    text PRIMARY KEY,
    bom_version_id        text NOT NULL REFERENCES bom_version (id),
    name                  text NOT NULL,
    display_currency      currency_code NOT NULL,
    labour_rate           money_amount NOT NULL CHECK (labour_rate >= 0),
    labour_rate_currency  currency_code NOT NULL,
    active_rules          text[] NOT NULL DEFAULT ARRAY['labour'],
    created_at            timestamptz NOT NULL DEFAULT now(),
    updated_at            timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE scenario_parameter (
    id                            text PRIMARY KEY,
    scenario_id                   text NOT NULL REFERENCES scenario (id) ON DELETE CASCADE,
    scope                         parameter_scope NOT NULL,
    part_ref                      part_reference NOT NULL,
    path                          text,
    supplier_id                   text REFERENCES supplier (id),
    plant_id                      text,
    purchase_currency             currency_code,
    price_override                money_amount CHECK (price_override IS NULL OR price_override >= 0),
    price_override_justification  text,
    labour_minutes                numeric(12, 4),
    created_at                    timestamptz NOT NULL DEFAULT now(),

    -- ADR-0002 : la portée est explicite. Un paramètre de portée chemin porte un
    -- chemin qui se termine par sa propre référence ; un paramètre de portée
    -- pièce n'en porte aucun.
    CONSTRAINT scope_path_consistency CHECK (
        (scope = 'path' AND path IS NOT NULL AND (path = part_ref OR path LIKE '%/' || part_ref))
     OR (scope = 'part' AND path IS NULL)
    ),

    -- Le prix forcé se justifie. Sans justification, il n'entre pas.
    CONSTRAINT override_requires_justification CHECK (
        price_override IS NULL
     OR (price_override_justification IS NOT NULL AND btrim(price_override_justification) <> '')
    ),

    CONSTRAINT plant_requires_supplier CHECK (plant_id IS NULL OR supplier_id IS NOT NULL),

    -- ADR-0010 : l'usine choisie appartient au fournisseur choisi.
    FOREIGN KEY (plant_id, supplier_id) REFERENCES supplier_plant (id, supplier_id)
);

-- Un seul paramètre par cible (pièce, ou occasion précise).
CREATE UNIQUE INDEX scenario_parameter_target_uq
    ON scenario_parameter (scenario_id, part_ref, coalesce(path, ''));

-- =============================================================================
-- 5. Calculs (I5)
-- =============================================================================

CREATE TABLE calculation (
    id                 text PRIMARY KEY,
    scenario_id        text NOT NULL REFERENCES scenario (id) ON DELETE CASCADE,
    bom_version_id     text NOT NULL REFERENCES bom_version (id),
    price_snapshot_id  text REFERENCES price_snapshot (id),
    rules_version      text NOT NULL,
    engine_version     text NOT NULL,
    active_rules       text[] NOT NULL,
    status             calculation_status NOT NULL,
    display_currency   currency_code NOT NULL,
    total_cost         money_amount,
    total_co2          co2_kg,
    input_digest       text NOT NULL,
    started_at         timestamptz NOT NULL,
    finished_at        timestamptz NOT NULL,

    CONSTRAINT completed_has_total CHECK (status = 'FAILED' OR total_cost IS NOT NULL)
);

COMMENT ON COLUMN calculation.input_digest IS
    'Empreinte des entrées : version de BOM, paramètres du scénario, snapshot, '
    'règles actives, version du moteur. Sert à deux choses : prouver la '
    'reproductibilité, et déterminer côté serveur si les totaux affichés sont '
    'obsolètes (api.md §6.2).';

COMMENT ON TABLE calculation IS
    'Une ligne est insérée une fois, complète, à la fin du calcul. L''état '
    '« calcul en cours » n''est pas persisté : en v1 le calcul est synchrone.';

-- Un calcul enregistré n'est jamais modifié. La suppression reste possible pour
-- que la suppression d'un scénario cascade (I5 porte sur la modification
-- rétroactive, pas sur la conservation éternelle).
CREATE TRIGGER calculation_no_update
    BEFORE UPDATE ON calculation
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

CREATE INDEX calculation_scenario_idx ON calculation (scenario_id, started_at DESC);
CREATE INDEX calculation_digest_idx   ON calculation (scenario_id, input_digest);

-- Vue agrégée persistée : une ligne par pièce (api.md §4.2).
CREATE TABLE calculation_line (
    calculation_id       text NOT NULL REFERENCES calculation (id) ON DELETE CASCADE,
    part_ref             part_reference NOT NULL,
    cumulative_quantity  quantity_value NOT NULL,
    unit                 text NOT NULL,
    -- `unit_cost` est le coût unitaire COMPLET (enfants inclus) : il s'affiche
    -- sur une ligne de l'arbre et ne se somme PAS entre niveaux.
    -- `own_contribution` est la contribution PROPRE (prix d'achat, ou la seule
    -- main-d'œuvre si la pièce est fabriquée) : c'est elle, et elle seule, dont
    -- la somme sur toutes les lignes égale le total du calcul.
    unit_cost            money_amount,
    own_unit_cost        money_amount,
    own_contribution     money_amount,
    own_co2_contribution co2_kg,
    occurrence_count     integer NOT NULL CHECK (occurrence_count > 0),
    price_status         text NOT NULL,
    supplier_id          text REFERENCES supplier (id),
    plant_id             text REFERENCES supplier_plant (id),

    PRIMARY KEY (calculation_id, part_ref)
);

CREATE INDEX calculation_line_contribution_idx
    ON calculation_line (calculation_id, own_contribution DESC);

-- Décomposition par système, calculée par le moteur et non par une requête :
-- sa somme doit être exactement le total (ADR-0007, ADR-0011).
CREATE TABLE calculation_system_total (
    calculation_id  text NOT NULL REFERENCES calculation (id) ON DELETE CASCADE,
    system          text NOT NULL,
    cost            money_amount NOT NULL,
    co2             co2_kg NOT NULL,
    cost_share_pct  numeric(5, 1) NOT NULL,
    co2_share_pct   numeric(5, 1) NOT NULL,

    PRIMARY KEY (calculation_id, system)
);

CREATE TABLE calculation_issue (
    id              bigserial PRIMARY KEY,
    calculation_id  text NOT NULL REFERENCES calculation (id) ON DELETE CASCADE,
    kind            calculation_issue_kind NOT NULL,
    part_ref        part_reference NOT NULL,
    detail          text NOT NULL
);

CREATE INDEX calculation_issue_calc_idx ON calculation_issue (calculation_id, kind);

INSERT INTO schema_migration (version) VALUES ('0001');

COMMIT;
