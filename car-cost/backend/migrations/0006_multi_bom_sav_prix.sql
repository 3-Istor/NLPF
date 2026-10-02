-- =============================================================================
-- 0006_multi_bom_sav_prix.sql — plusieurs nomenclatures, SAV, snapshots par BOM
--
--   ADR-0015 : quatre nomenclatures coexistent (Multipla + trois Valhalla). Un
--             snapshot de prix appartient à une nomenclature : sans ce lien, le
--             dernier snapshot pris pour le Multipla servait au calcul d'une
--             Valhalla, et toutes ses pièces sortaient sans prix.
--
--   SAV     : une arête porte, à côté de sa quantité montée, la quantité de
--             pièces de rechange livrées avec le véhicule. Le scénario décide
--             s'il la compte.
--
-- Aucune règle ici : la base garde les valeurs et leurs bornes ; additionner
-- montée et SAV appartient à l'application.
-- =============================================================================

BEGIN;

-- Le défaut remplit les arêtes existantes sans UPDATE : le déclencheur qui fige
-- une version validée (0003) ne voit passer aucune écriture de ligne.
ALTER TABLE bom_edge
    ADD COLUMN after_sales_quantity quantity_value NOT NULL DEFAULT 0
        CHECK (after_sales_quantity >= 0);

COMMENT ON COLUMN bom_edge.after_sales_quantity IS
    'Pièces de rechange livrées avec le véhicule (SAV), en plus de la quantité '
    'montée. N''entrent dans le calcul que si le scénario active le SAV.';

-- Nullable : un snapshot pris avant cette migration ne disait pas pour quelle
-- nomenclature il l'était. Le remplir après coup serait le modifier, ce que le
-- déclencheur d'immuabilité refuse — à raison.
ALTER TABLE price_snapshot
    ADD COLUMN bom_version_id text REFERENCES bom_version (id);

CREATE INDEX price_snapshot_bom_idx ON price_snapshot (bom_version_id, taken_at DESC);

ALTER TABLE scenario
    ADD COLUMN include_after_sales boolean NOT NULL DEFAULT false;

-- La copie figée dit si le SAV était compté (ADR-0014 : un snapshot de calcul
-- s'explique sans relire le scénario vivant). Ajoutée par défaut à false, ce
-- que valaient tous les gels antérieurs : le déclencheur qui fige la ligne ne
-- voit passer aucune écriture.
ALTER TABLE calculation_snapshot
    ADD COLUMN include_after_sales boolean NOT NULL DEFAULT false;

-- Le taux horaire de référence de la nomenclature, proposé à la création d'un
-- scénario (42 EUR/h à Turin, 60 EUR/h à Gaydon). Le défaut ne sert qu'à
-- remplir la seule version qui pouvait exister avant cette migration, le
-- Multipla, puis il est retiré : une nouvelle version doit dire le sien.
ALTER TABLE bom_version
    ADD COLUMN reference_labour_rate numeric(12, 2) DEFAULT 42.00
        CHECK (reference_labour_rate > 0);
ALTER TABLE bom_version ALTER COLUMN reference_labour_rate DROP DEFAULT;

INSERT INTO schema_migration (version) VALUES ('0006');

COMMIT;
