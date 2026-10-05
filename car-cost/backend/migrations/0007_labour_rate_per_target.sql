-- =============================================================================
-- 0007_labour_rate_per_target.sql — un taux horaire par pièce ou par occurrence
--
--   ADR-0016 : un paramètre de scénario peut porter son propre taux horaire, à
--             la place de celui du scénario, sur la cible qu'il vise (ADR-0002).
--
-- Aucune règle ici : la base garde la valeur et sa borne. Choisir quel taux
-- s'applique, et le multiplier par un temps, appartient au domaine (ADR-0007).
-- =============================================================================

BEGIN;

-- Nullable : sans valeur, c'est le taux du scénario qui s'applique.
ALTER TABLE scenario_parameter
    ADD COLUMN labour_rate money_amount CHECK (labour_rate IS NULL OR labour_rate >= 0);

-- La copie figée reprend la colonne : sans elle, un snapshot de calcul ne
-- dirait plus quel taux a servi (ADR-0014). Ajouter une colonne nulle ne
-- réécrit aucune ligne : le déclencheur qui fige la copie ne voit rien passer.
ALTER TABLE calculation_snapshot_parameter
    ADD COLUMN labour_rate money_amount CHECK (labour_rate IS NULL OR labour_rate >= 0);

INSERT INTO schema_migration (version) VALUES ('0007');

COMMIT;
