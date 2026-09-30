-- =============================================================================
-- 0002 — Coûts de contexte d'un calcul (portée « chemin », ADR-0002)
-- =============================================================================
--
-- Une ligne de `calculation_line` porte UN coût unitaire par pièce. Dès qu'une
-- surcharge de chemin existe, ce coût est une moyenne pondérée : juste pour la
-- contribution, faux pour chaque occurrence prise isolément. L'arbre est servi
-- depuis le calcul relu ; sans cette table, il afficherait la moyenne sur
-- l'occurrence surchargée et l'écran contredirait le réglage.
--
-- Deux sortes de lignes, écrites seulement quand une surcharge de chemin existe :
--   - `path` : les préfixes des chemins surchargés, les seuls contextes dont le
--     coût diffère ;
--   - `part` : le coût de référence d'une pièce (sans surcharge de chemin) quand
--     il diffère de la moyenne portée par `calculation_line`.
-- Aucun coût n'est calculé ici (ADR-0007) : le moteur les produit, la table les
-- conserve.

BEGIN;

CREATE TABLE calculation_context_cost (
    calculation_id  text NOT NULL REFERENCES calculation (id) ON DELETE CASCADE,
    scope           text NOT NULL CHECK (scope IN ('part', 'path')),
    -- Référence de pièce pour `part`, chemin complet depuis la racine pour `path`.
    target          text NOT NULL,
    -- NULL quand un prix manque dans ce contexte : jamais un zéro.
    own_unit_cost   money_amount,
    full_unit_cost  money_amount,

    PRIMARY KEY (calculation_id, scope, target)
);

INSERT INTO schema_migration (version) VALUES ('0002');

COMMIT;
