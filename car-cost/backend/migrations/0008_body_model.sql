-- =============================================================================
-- 0008_body_model.sql — un modèle 3D par version, une densité par pièce
--
--   ADR-0017 : la maquette 3D d'un véhicule est rattachée à sa version, et une
--             variante de carrosserie importée garde la trace de sa parente.
--
-- Aucune règle ici : la base garde la densité, la parenté et le fichier, et
-- vérifie seulement leur forme (densité > 0, parente existante, somme de
-- contrôle exacte). Mesurer un volume et en tirer une masse appartient au
-- domaine. Les densités sont synthétiques ; cette migration n'en remplit
-- aucune : une base existante repart d'une base vide (README, docker compose
-- down -v).
-- =============================================================================

BEGIN;

-- Nullable : une pièce sans densité n'est pas mesurable depuis un modèle 3D.
-- Ajouter une colonne nulle ne réécrit aucune ligne : les déclencheurs de 0003
-- ne voient rien passer, les versions validées restent intactes.
ALTER TABLE part
    ADD COLUMN density_kg_m3 numeric(10, 3)
        CHECK (density_kg_m3 IS NULL OR density_kg_m3 > 0);

-- La version dont une variante dérive ; NULL pour une nomenclature d'origine.
ALTER TABLE bom_version
    ADD COLUMN parent_version_id text REFERENCES bom_version (id),
    ADD CONSTRAINT bom_version_parent_not_self
        CHECK (parent_version_id IS NULL OR parent_version_id <> id);

-- Le modèle d'une version : écrit une fois, jamais modifié. Rattacher un modèle
-- à une version validée reste permis : il ne touche ni part, ni bom_edge, ni
-- part_supplier.
CREATE TABLE bom_model (
    bom_version_id text PRIMARY KEY REFERENCES bom_version (id),
    glb            bytea NOT NULL CHECK (octet_length(glb) > 0),
    -- Intégrité du fichier, pas une règle métier.
    sha256         text NOT NULL CHECK (sha256 = encode(sha256(glb), 'hex')),
    source         text NOT NULL CHECK (source IN ('generated', 'imported')),
    created_at     timestamptz NOT NULL DEFAULT now()
);

CREATE TRIGGER bom_model_immutable
    BEFORE UPDATE OR DELETE ON bom_model
    FOR EACH ROW EXECUTE FUNCTION forbid_mutation();

INSERT INTO schema_migration (version) VALUES ('0008');

COMMIT;
