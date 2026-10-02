-- =============================================================================
-- 0005_derived_from_calculation_snapshot.sql — repartir d'un snapshot de calcul
--
--   ADR-0014, complément du 01/10/2026 : « Repartir de ce snapshot » crée un
--             scénario neuf avec les réglages copiés dans le snapshot. Le
--             scénario garde la trace du snapshot d'où il part, et un gel de
--             ce scénario la recopie : le nouveau snapshot dit d'où il vient
--             sans relire le scénario vivant.
--
-- Deux colonnes, aucune règle : c'est l'application qui pose et recopie le
-- lien ; la base garantit seulement qu'il désigne un snapshot qui existe.
-- =============================================================================

BEGIN;

-- Sans cascade : un snapshot de calcul ne se supprime pas (0004), le lien ne
-- peut donc pas pendre.
ALTER TABLE scenario
    ADD COLUMN derived_from text REFERENCES calculation_snapshot (id);

-- Copie au gel. Figée comme le reste de la ligne : le déclencheur
-- `calculation_snapshot_only_name_changes` compare la ligne entière.
ALTER TABLE calculation_snapshot
    ADD COLUMN derived_from text REFERENCES calculation_snapshot (id);

INSERT INTO schema_migration (version) VALUES ('0005');

COMMIT;
