-- =============================================================================
-- 0003_validated_bom_is_frozen.sql — une version validée ne change plus
--
--   ADR-0013  Une version de nomenclature validée est immuable ; on en charge
--             une nouvelle plutôt que de corriger l'ancienne.
--
-- `validated_at` atteste qu'un graphe précis a passé ses contrôles. Si l'on
-- pouvait ensuite ajouter une arête ou changer une quantité, l'attestation
-- porterait sur un graphe qui n'existe plus, et un calcul enregistré ne
-- pourrait plus être rejoué. C'est aussi ce qui autorise l'application à garder
-- une version en mémoire sans jamais la relire.
--
-- Le chargeur n'est pas gêné : il écrit pièces, arêtes et fournisseurs dans la
-- même transaction, AVANT de renseigner `validated_at`.
-- =============================================================================

BEGIN;

CREATE FUNCTION forbid_change_to_validated_bom() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    touched text[];
BEGIN
    IF TG_OP = 'INSERT' THEN
        touched := ARRAY[NEW.bom_version_id];
    ELSIF TG_OP = 'DELETE' THEN
        touched := ARRAY[OLD.bom_version_id];
    ELSE
        -- Déplacer une ligne d'une version à l'autre toucherait les deux.
        touched := ARRAY(SELECT DISTINCT unnest(
            ARRAY[OLD.bom_version_id, NEW.bom_version_id]));
    END IF;

    IF EXISTS (
        SELECT 1 FROM bom_version
        WHERE id = ANY (touched) AND validated_at IS NOT NULL
    ) THEN
        RAISE EXCEPTION '% : la version % est validée, donc figée (ADR-0013) : '
            'opération % refusée ; charger une nouvelle version',
            TG_TABLE_NAME, touched, TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END IF;

    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER part_frozen_once_validated
    BEFORE INSERT OR UPDATE OR DELETE ON part
    FOR EACH ROW EXECUTE FUNCTION forbid_change_to_validated_bom();

CREATE TRIGGER bom_edge_frozen_once_validated
    BEFORE INSERT OR UPDATE OR DELETE ON bom_edge
    FOR EACH ROW EXECUTE FUNCTION forbid_change_to_validated_bom();

-- Le multiplicateur fournisseur entre dans le prix unitaire (ADR-0010) : le
-- changer après coup rendrait faux l'`/explain` d'un calcul enregistré.
CREATE TRIGGER part_supplier_frozen_once_validated
    BEFORE INSERT OR UPDATE OR DELETE ON part_supplier
    FOR EACH ROW EXECUTE FUNCTION forbid_change_to_validated_bom();

-- Sur la version elle-même : le seul changement permis est celui qui la
-- valide. Une fois validée, ni modification, ni suppression — un identifiant
-- réutilisé pour un autre graphe tromperait tout ce qui l'a gardé en mémoire.
CREATE FUNCTION forbid_change_to_validated_bom_version() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF OLD.validated_at IS NOT NULL THEN
        RAISE EXCEPTION 'bom_version % est validée, donc figée (ADR-0013) : '
            'opération % refusée', OLD.id, TG_OP
            USING ERRCODE = 'insufficient_privilege';
    END IF;
    RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
END;
$$;

CREATE TRIGGER bom_version_frozen_once_validated
    BEFORE UPDATE OR DELETE ON bom_version
    FOR EACH ROW EXECUTE FUNCTION forbid_change_to_validated_bom_version();

INSERT INTO schema_migration (version) VALUES ('0003');

COMMIT;
