-- =============================================================================
-- 0004_calculation_snapshot.sql — un snapshot de calcul nommé, figé
--
--   ADR-0014  Un snapshot de calcul fige un calcul et les hypothèses qui l'ont
--             produit ; il se suffit à lui-même, seul son nom change.
--
-- À ne pas confondre avec le snapshot de PRIX (`price_snapshot`, ADR-0003),
-- que celui-ci référence.
--
-- Trois tables :
--   calculation_snapshot            le gel : références et hypothèses copiées ;
--   calculation_snapshot_parameter  la copie des paramètres appliqués ;
--   calculation_snapshot_name       la trace des noms, en ajout seul.
--
-- Rien ici ne calcule ni ne plie : `name_key` est calculé par l'application
-- (le pliage de la recherche) ; la base se contente d'en garantir l'unicité.
-- =============================================================================

BEGIN;

CREATE TABLE calculation_snapshot (
    id                 text PRIMARY KEY,

    -- ADR-0014 : nom obligatoire, sans valeur de repli.
    name               text NOT NULL CHECK (btrim(name) <> ''),
    -- Clé d'unicité calculée par l'application : fold(name).
    name_key           text NOT NULL CHECK (name_key <> ''),

    -- Références. Aucune n'est en cascade : ce que le gel désigne ne peut pas
    -- disparaître sous lui. En particulier, supprimer le scénario cascaderait
    -- vers `calculation`, que l'on référence ici : la suppression d'un
    -- scénario porteur est donc refusée (ADR-0014, SCENARIO_HAS_SNAPSHOTS).
    bom_version_id     text NOT NULL REFERENCES bom_version (id),
    scenario_id        text NOT NULL REFERENCES scenario (id),
    -- Un calcul ne se fige qu'une fois : figer, c'est lancer un calcul neuf.
    calculation_id     text NOT NULL UNIQUE REFERENCES calculation (id),
    price_snapshot_id  text NOT NULL REFERENCES price_snapshot (id),

    -- Copies : le gel se relit sans le scénario vivant (ADR-0014, autonomie).
    scenario_name      text NOT NULL,
    display_currency   currency_code NOT NULL,
    labour_rate        money_amount NOT NULL CHECK (labour_rate >= 0),
    active_rules       text[] NOT NULL,
    created_at         timestamptz NOT NULL,

    -- ADR-0014 : un nom unique par version de nomenclature, sans casse ni
    -- accents (la clé arrive déjà pliée).
    CONSTRAINT calculation_snapshot_name_uq UNIQUE (bom_version_id, name_key)
);

CREATE INDEX calculation_snapshot_scenario_idx ON calculation_snapshot (scenario_id);

-- ADR-0014 : immuable, sauf le nom. La comparaison se fait sur la ligne
-- entière, privée de `name` et `name_key` : une colonne ajoutée plus tard est
-- figée d'office.
CREATE FUNCTION forbid_change_to_calculation_snapshot() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF to_jsonb(NEW) - 'name' - 'name_key'
       IS DISTINCT FROM to_jsonb(OLD) - 'name' - 'name_key' THEN
        RAISE EXCEPTION 'calculation_snapshot % est figé (ADR-0014) : '
            'seul le nom se change', OLD.id
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN NEW;
END;
$$;

CREATE TRIGGER calculation_snapshot_only_name_changes
    BEFORE UPDATE ON calculation_snapshot
    FOR EACH ROW EXECUTE FUNCTION forbid_change_to_calculation_snapshot();

-- ADR-0014 : la suppression d'un snapshot de calcul est refusée.
CREATE TRIGGER calculation_snapshot_no_delete
    BEFORE DELETE ON calculation_snapshot
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- Copie des paramètres exactement appliqués. Mêmes garanties d'intégrité que
-- `scenario_parameter`, dont elle reprend les colonnes, sans son identifiant :
-- la copie ne pointe pas vers le scénario vivant.
CREATE TABLE calculation_snapshot_parameter (
    snapshot_id                   text NOT NULL REFERENCES calculation_snapshot (id),
    scope                         parameter_scope NOT NULL,
    part_ref                      part_reference NOT NULL,
    path                          text,
    supplier_id                   text REFERENCES supplier (id),
    plant_id                      text,
    purchase_currency             currency_code,
    price_override                money_amount CHECK (price_override IS NULL OR price_override >= 0),
    price_override_justification  text,
    labour_minutes                numeric(12, 4),

    -- ADR-0002 : portée explicite, chemin terminé par la référence visée.
    CONSTRAINT snapshot_scope_path_consistency CHECK (
        (scope = 'path' AND path IS NOT NULL AND (path = part_ref OR path LIKE '%/' || part_ref))
     OR (scope = 'part' AND path IS NULL)
    ),

    -- Le prix forcé se justifie, dans la copie comme dans l'original.
    CONSTRAINT snapshot_override_requires_justification CHECK (
        price_override IS NULL
     OR (price_override_justification IS NOT NULL AND btrim(price_override_justification) <> '')
    ),

    CONSTRAINT snapshot_plant_requires_supplier CHECK (plant_id IS NULL OR supplier_id IS NOT NULL),

    -- ADR-0010 : l'usine copiée appartient au fournisseur copié.
    FOREIGN KEY (plant_id, supplier_id) REFERENCES supplier_plant (id, supplier_id)
);

-- Un seul paramètre par cible, comme dans le scénario d'origine.
CREATE UNIQUE INDEX calculation_snapshot_parameter_target_uq
    ON calculation_snapshot_parameter (snapshot_id, part_ref, coalesce(path, ''));

-- ADR-0014 : les hypothèses figées ne changent plus.
CREATE TRIGGER calculation_snapshot_parameter_no_mutation
    BEFORE UPDATE OR DELETE ON calculation_snapshot_parameter
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

-- ADR-0014 : chaque nom porté, depuis la création ; un renommage s'ajoute.
-- `seq` ordonne les noms quand deux horodatages se confondent.
CREATE TABLE calculation_snapshot_name (
    seq          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    snapshot_id  text NOT NULL REFERENCES calculation_snapshot (id),
    name         text NOT NULL CHECK (btrim(name) <> ''),
    renamed_at   timestamptz NOT NULL
);

CREATE INDEX calculation_snapshot_name_snapshot_idx
    ON calculation_snapshot_name (snapshot_id, seq);

-- ADR-0014 : la trace des renommages est en ajout seul.
CREATE TRIGGER calculation_snapshot_name_append_only
    BEFORE UPDATE OR DELETE ON calculation_snapshot_name
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

INSERT INTO schema_migration (version) VALUES ('0004');

COMMIT;
