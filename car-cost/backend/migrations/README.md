# Migrations

Des fichiers SQL numérotés, appliqués **dans l'ordre lexicographique**, chacun dans une transaction,
chacun terminé par son `INSERT INTO schema_migration`.

```
0001_initial_schema.sql
0002_....sql
```

## Règles

- Une migration appliquée n'est **jamais** modifiée : on en écrit une nouvelle.
- Chaque contrainte porte en commentaire la décision ou l'invariant qu'elle fait respecter. Une
  contrainte sans justification n'entre pas.
- Le SQL contient des contraintes d'**intégrité**, jamais de règle de **coût** : celles-ci vivent
  dans le domaine ([ADR-0007](../../docs/adr/0007-sql-lit-le-graphe-le-code-calcule.md)).

## Pourquoi du SQL brut et pas Alembic

L'autogénération d'Alembic part des modèles SQLAlchemy ; or ce schéma repose sur des constructions
qu'elle ne produit pas : clés étrangères composites portant le mode de valorisation, index uniques
partiels, déclencheurs d'immuabilité, domaines. Il faudrait les écrire à la main dans des
`op.execute(...)` — autant écrire du SQL lisible.

Si Alembic est adopté plus tard, chaque fichier devient un `op.execute` d'une révision ; rien n'est
perdu. Ce n'est pas une décision structurante, donc pas d'ADR.

## Application

```bash
psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f 0001_initial_schema.sql
```

## Ce que le schéma garantit, et ce qu'il ne garantit pas

| Propriété | Garantie par |
|---|---|
| Une paire (parent, enfant) est unique | Clé primaire de `bom_edge` |
| Une pièce achetée n'a pas d'enfant | Clé étrangère composite `bom_edge → part(…, valuation_mode)` |
| Une pièce achetée a un prix, une fabriquée n'en a pas | `CHECK` sur `part` |
| Un ensemble fabriqué n'a pas de fournisseur | Clé étrangère composite `part_supplier → part(…, valuation_mode)` |
| L'usine choisie appartient au fournisseur choisi | Clé étrangère composite vers `supplier_plant (id, supplier_id)` |
| Un prix forcé porte une justification | `CHECK` sur `scenario_parameter` |
| Un snapshot n'est jamais modifié | Déclencheur `forbid_mutation` |
| **Acyclicité** | ❌ Impossible en déclaratif — tri topologique au chargement |
| **Racine unique** | ❌ Contrôle au chargement |
| **Aucun orphelin** | ❌ Contrôle au chargement |

Les trois dernières lignes sont la raison d'être de `bom_version.validated_at` : tant qu'il est
`NULL`, l'application refuse tout calcul sur cette version.
