-- Contrôle des garanties du schéma.
--
-- Chaque cas tente une écriture INTERDITE et annonce si la base l'a refusée.
-- Un « refusé » est un succès ; un WARNING signale une contrainte qui ne tient
-- pas. Tout est annulé à la fin : la base reste dans l'état où on l'a trouvée.
--
--   docker compose exec -T db psql -U 3istor -d 3istor -q --       < backend/migrations/checks/contraintes.sql
--
-- Attendu : 26 refus, 0 WARNING, 2 paramètres valides acceptés, un renommage
-- de snapshot de calcul accepté.
\set ON_ERROR_STOP on
\pset pager off

BEGIN;

INSERT INTO bom_version
    (id, label, root_part_ref, generator_version, seed_checksum, part_count, edge_count)
VALUES ('t', 'test', 'ROOT', '1.0.0', 'sha256:x', 3, 1);

INSERT INTO part
    (bom_version_id, part_ref, label, category, system, unit, valuation_mode,
     labour_minutes, base_price_eur, carbon_factor_kg_co2e_per_unit,
     expected_cumulative_quantity)
VALUES
    ('t', 'ROOT',  'Racine',   'vehicle',  'VEH', 'pce', 'manufactured', 10, NULL, 1, 1),
    ('t', 'SUBASM','Ensemble', 'engine',   'GMP', 'pce', 'manufactured',  5, NULL, 1, 1),
    ('t', 'SCREW', 'Vis',      'fastener', 'FIX', 'pce', 'purchased',   NULL, 0.5, 0.1, 4);

INSERT INTO bom_edge
    (bom_version_id, parent_ref, child_ref, parent_valuation_mode, quantity, unit)
VALUES ('t', 'ROOT', 'SCREW', 'manufactured', 4, 'pce');

INSERT INTO supplier (id, name, home_country) VALUES ('SUP', 'Test SpA', 'IT');
INSERT INTO supplier_plant
    (id, supplier_id, label, origin_country, price_coefficient, lead_time_days,
     transport_co2_kg_per_kg, is_default)
VALUES ('PLT-IT', 'SUP', 'Turin', 'IT', 1.0, 10, 0.02, true),
       ('PLT-TR', 'SUP', 'Bursa', 'TR', 0.92, 34, 0.14, false);
INSERT INTO supplier (id, name, home_country) VALUES ('OTHER', 'Autre', 'DE');
INSERT INTO supplier_plant
    (id, supplier_id, label, origin_country, price_coefficient, lead_time_days,
     transport_co2_kg_per_kg, is_default)
VALUES ('PLT-DE', 'OTHER', 'Hagen', 'DE', 1.0, 15, 0.05, true);

INSERT INTO price_snapshot (id, taken_at, source, status, counts)
VALUES ('snp', now(), 'mock', 'FRESH', '{}'::jsonb);

INSERT INTO scenario
    (id, bom_version_id, name, display_currency, labour_rate, labour_rate_currency)
VALUES ('scn', 't', 'test', 'EUR', 42, 'EUR');

CREATE OR REPLACE FUNCTION doit_refuser(intitule text, requete text) RETURNS void
LANGUAGE plpgsql AS $fn$
BEGIN
    BEGIN
        EXECUTE requete;
        RAISE WARNING '  ACCEPTÉ — LA CONTRAINTE NE TIENT PAS : %', intitule;
    EXCEPTION WHEN others THEN
        RAISE NOTICE '  refusé : % (%)', intitule, left(SQLERRM, 90);
    END;
END;
$fn$;

SELECT doit_refuser(
    'enfant sous une pièce achetée (ADR-0008)',
    $q$INSERT INTO bom_edge (bom_version_id, parent_ref, child_ref,
        parent_valuation_mode, quantity, unit)
       VALUES ('t', 'SCREW', 'SUBASM', 'purchased', 1, 'pce')$q$);

SELECT doit_refuser(
    'enfant sous une pièce achetée, mode falsifié dans l''arête',
    $q$INSERT INTO bom_edge (bom_version_id, parent_ref, child_ref,
        parent_valuation_mode, quantity, unit)
       VALUES ('t', 'SCREW', 'SUBASM', 'manufactured', 1, 'pce')$q$);

SELECT doit_refuser(
    'arête en double (invariant I3)',
    $q$INSERT INTO bom_edge (bom_version_id, parent_ref, child_ref,
        parent_valuation_mode, quantity, unit)
       VALUES ('t', 'ROOT', 'SCREW', 'manufactured', 9, 'pce')$q$);

SELECT doit_refuser(
    'prix propre sur un ensemble fabriqué (ADR-0008)',
    $q$INSERT INTO part (bom_version_id, part_ref, label, category, system, unit,
        valuation_mode, labour_minutes, base_price_eur,
        carbon_factor_kg_co2e_per_unit, expected_cumulative_quantity)
       VALUES ('t', 'BAD1', 'x', 'engine', 'GMP', 'pce', 'manufactured', 5, 12.0, 1, 1)$q$);

SELECT doit_refuser(
    'pièce achetée sans prix (ADR-0008)',
    $q$INSERT INTO part (bom_version_id, part_ref, label, category, system, unit,
        valuation_mode, labour_minutes, base_price_eur,
        carbon_factor_kg_co2e_per_unit, expected_cumulative_quantity)
       VALUES ('t', 'BAD2', 'x', 'fastener', 'FIX', 'pce', 'purchased', NULL, NULL, 1, 1)$q$);

SELECT doit_refuser(
    'fournisseur sur un ensemble fabriqué (ADR-0008)',
    $q$INSERT INTO part_supplier (bom_version_id, part_ref, part_valuation_mode,
        supplier_id, price_multiplier)
       VALUES ('t', 'SUBASM', 'manufactured', 'SUP', 1.0)$q$);

SELECT doit_refuser(
    'usine qui n''appartient pas au fournisseur choisi (ADR-0010)',
    $q$INSERT INTO scenario_parameter (id, scenario_id, scope, part_ref,
        supplier_id, plant_id)
       VALUES ('p1', 'scn', 'part', 'SCREW', 'SUP', 'PLT-DE')$q$);

SELECT doit_refuser(
    'prix forcé sans justification',
    $q$INSERT INTO scenario_parameter (id, scenario_id, scope, part_ref, price_override)
       VALUES ('p2', 'scn', 'part', 'SCREW', 9.99)$q$);

SELECT doit_refuser(
    'portée « chemin » sans chemin (ADR-0002)',
    $q$INSERT INTO scenario_parameter (id, scenario_id, scope, part_ref)
       VALUES ('p3', 'scn', 'path', 'SCREW')$q$);

SELECT doit_refuser(
    'chemin qui ne finit pas sur la pièce visée (ADR-0002)',
    $q$INSERT INTO scenario_parameter (id, scenario_id, scope, part_ref, path)
       VALUES ('p4', 'scn', 'path', 'SCREW', 'ROOT/SUBASM')$q$);

SELECT doit_refuser(
    'modification d''un snapshot enregistré (ADR-0003)',
    $q$UPDATE price_snapshot SET source = 'falsifié' WHERE id = 'snp'$q$);

SELECT doit_refuser(
    'suppression d''un snapshot enregistré (ADR-0003)',
    $q$DELETE FROM price_snapshot WHERE id = 'snp'$q$);

SELECT doit_refuser(
    'quantité d''arête nulle',
    $q$INSERT INTO bom_edge (bom_version_id, parent_ref, child_ref,
        parent_valuation_mode, quantity, unit)
       VALUES ('t', 'SUBASM', 'SCREW', 'manufactured', 0, 'pce')$q$);

SELECT doit_refuser(
    'référence hors de [A-Z0-9-]+ (chemins transportables en URL)',
    $q$INSERT INTO part (bom_version_id, part_ref, label, category, system, unit,
        valuation_mode, base_price_eur, carbon_factor_kg_co2e_per_unit,
        expected_cumulative_quantity)
       VALUES ('t', 'vis/m6', 'x', 'fastener', 'FIX', 'pce', 'purchased', 1, 1, 1)$q$);

-- Ce qui DOIT passer : la portée chemin bien formée, et le prix forcé justifié.
INSERT INTO scenario_parameter (id, scenario_id, scope, part_ref, path)
VALUES ('ok1', 'scn', 'path', 'SCREW', 'ROOT/SCREW');
INSERT INTO scenario_parameter
    (id, scenario_id, scope, part_ref, price_override, price_override_justification)
VALUES ('ok2', 'scn', 'part', 'SCREW', 9.99, 'devis fournisseur du 2026-09-20');
SELECT doit_refuser(
    'deux paramètres sur la même cible',
    $q$INSERT INTO scenario_parameter (id, scenario_id, scope, part_ref, path)
       VALUES ('dup', 'scn', 'path', 'SCREW', 'ROOT/SCREW')$q$);

-- Une version validée est figée (ADR-0013). On la valide ici, ce qui doit
-- passer, puis on tente de la retoucher par chaque table qui la compose.
INSERT INTO part_supplier (bom_version_id, part_ref, part_valuation_mode,
    supplier_id, price_multiplier, is_default)
VALUES ('t', 'SCREW', 'purchased', 'SUP', 1.0, true);
UPDATE bom_version SET validated_at = now() WHERE id = 't';

SELECT doit_refuser(
    'quantité changée sur une version validée (ADR-0013)',
    $q$UPDATE bom_edge SET quantity = 5 WHERE bom_version_id = 't'$q$);

SELECT doit_refuser(
    'arête ajoutée à une version validée (ADR-0013)',
    $q$INSERT INTO bom_edge (bom_version_id, parent_ref, child_ref,
        parent_valuation_mode, quantity, unit)
       VALUES ('t', 'ROOT', 'SUBASM', 'manufactured', 1, 'pce')$q$);

SELECT doit_refuser(
    'pièce retirée d''une version validée (ADR-0013)',
    $q$DELETE FROM part WHERE bom_version_id = 't' AND part_ref = 'SUBASM'$q$);

SELECT doit_refuser(
    'multiplicateur fournisseur changé sur une version validée (ADR-0013)',
    $q$UPDATE part_supplier SET price_multiplier = 2 WHERE bom_version_id = 't'$q$);

SELECT doit_refuser(
    'version validée retouchée (ADR-0013)',
    $q$UPDATE bom_version SET root_part_ref = 'SUBASM' WHERE id = 't'$q$);

SELECT doit_refuser(
    'version validée supprimée (ADR-0013)',
    $q$DELETE FROM bom_version WHERE id = 't'$q$);

-- Un snapshot de calcul est figé, sauf son nom (ADR-0014). On fige un calcul
-- du scénario sur la version validée, ce qui doit passer, puis on tente de le
-- retoucher.
INSERT INTO calculation
    (id, scenario_id, bom_version_id, price_snapshot_id, rules_version,
     engine_version, active_rules, status, display_currency, total_cost,
     input_digest, started_at, finished_at)
VALUES ('calc1', 'scn', 't', 'snp', 'r1', 'e1', ARRAY['labour'], 'OK', 'EUR', 100,
        'sha256:x', now(), now()),
       ('calc2', 'scn', 't', 'snp', 'r1', 'e1', ARRAY['labour'], 'OK', 'EUR', 100,
        'sha256:x', now(), now());
INSERT INTO calculation_snapshot
    (id, name, name_key, bom_version_id, scenario_id, scenario_name,
     calculation_id, price_snapshot_id, display_currency, labour_rate,
     active_rules, created_at)
VALUES ('cs1', 'Gel de référence', 'gel de reference', 't', 'scn', 'test',
        'calc1', 'snp', 'EUR', 42, ARRAY['labour'], now());

UPDATE calculation_snapshot SET name = 'Gel retenu', name_key = 'gel retenu'
WHERE id = 'cs1';
SELECT '  accepté (comme attendu) : renommage du snapshot de calcul en « '
       || name || ' »' AS resultat
FROM calculation_snapshot WHERE id = 'cs1';

SELECT doit_refuser(
    'colonne figée d''un snapshot de calcul modifiée (ADR-0014)',
    $q$UPDATE calculation_snapshot SET labour_rate = 99 WHERE id = 'cs1'$q$);

SELECT doit_refuser(
    'snapshot de calcul supprimé (ADR-0014)',
    $q$DELETE FROM calculation_snapshot WHERE id = 'cs1'$q$);

SELECT doit_refuser(
    'nom de snapshot de calcul en double dans la version (ADR-0014)',
    $q$INSERT INTO calculation_snapshot
        (id, name, name_key, bom_version_id, scenario_id, scenario_name,
         calculation_id, price_snapshot_id, display_currency, labour_rate,
         active_rules, created_at)
       VALUES ('cs2', 'GEL RETENU', 'gel retenu', 't', 'scn', 'test',
         'calc2', 'snp', 'EUR', 42, ARRAY['labour'], now())$q$);

SELECT doit_refuser(
    'scénario porteur d''un snapshot de calcul supprimé (ADR-0014)',
    $q$DELETE FROM scenario WHERE id = 'scn'$q$);

SELECT doit_refuser(
    'scénario reparti d''un snapshot de calcul inexistant (ADR-0014, 0005)',
    $q$UPDATE scenario SET derived_from = 'cs-inconnu' WHERE id = 'scn'$q$);

SELECT '  accepté (comme attendu) : ' || count(*)::text ||
       ' paramètres valides' AS resultat
FROM scenario_parameter;

ROLLBACK;

SELECT count(*) AS tables_creees
FROM information_schema.tables
WHERE table_schema = 'public' AND table_type = 'BASE TABLE';
