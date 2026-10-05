# Migrations

Des fichiers SQL numérotés, appliqués **dans l'ordre lexicographique**, chacun dans une transaction,
chacun terminé par son `INSERT INTO schema_migration`.

```
0001_initial_schema.sql
0002_calculation_context_cost.sql   coûts par occurrence quand une surcharge de chemin existe
0003_validated_bom_is_frozen.sql    une version validée ne change plus (ADR-0013)
0004_calculation_snapshot.sql       un snapshot de calcul nommé, figé sauf son nom (ADR-0014)
0005_derived_from_calculation_snapshot.sql  le snapshot d'où repart un scénario, recopié au gel (ADR-0014)
0006_multi_bom_sav_prix.sql         plusieurs nomenclatures, SAV, snapshots de prix par BOM (ADR-0015)
0007_labour_rate_per_target.sql     un taux horaire par pièce ou par chemin (ADR-0016)
```

Postgres ne les exécute qu'à la **création** du volume. Le conteneur `backend` rattrape à chaque
démarrage celles qui manquent dans `schema_migration` (`carcost.infrastructure.startup`). Hors
conteneur, sur une base existante, les appliquer à la main :

```bash
docker compose exec -T db psql -U 3istor -d 3istor -v ON_ERROR_STOP=1 -q \
  < backend/migrations/0002_calculation_context_cost.sql
docker compose exec -T db psql -U 3istor -d 3istor -v ON_ERROR_STOP=1 -q \
  < backend/migrations/0003_validated_bom_is_frozen.sql
docker compose exec -T db psql -U 3istor -d 3istor -v ON_ERROR_STOP=1 -q \
  < backend/migrations/0004_calculation_snapshot.sql
docker compose exec -T db psql -U 3istor -d 3istor -v ON_ERROR_STOP=1 -q \
  < backend/migrations/0005_derived_from_calculation_snapshot.sql
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
for migration in 0*.sql; do psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$migration"; done
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
| Une version validée n'est plus modifiée ni supprimée (ADR-0013) | Déclencheurs `*_frozen_once_validated` (0003) |
| Un snapshot de calcul ne change que de nom (ADR-0014) | Déclencheur `calculation_snapshot_only_name_changes` (0004) |
| Un snapshot de calcul n'est jamais supprimé, ni ses paramètres copiés modifiés (ADR-0014) | Déclencheurs `forbid_mutation` sur `calculation_snapshot` (suppression) et `calculation_snapshot_parameter` (0004) |
| La trace des noms d'un snapshot de calcul est en ajout seul (ADR-0014) | Déclencheur `forbid_mutation` sur `calculation_snapshot_name` (0004) |
| Deux snapshots de calcul d'une même version n'ont pas le même nom, sans casse ni accents (ADR-0014) | `UNIQUE (bom_version_id, name_key)` ; `name_key` est plié par l'application (0004) |
| Un scénario qui porte un snapshot de calcul ne se supprime pas (ADR-0014) | Clés étrangères sans cascade de `calculation_snapshot` vers `scenario` et `calculation` (0004) |
| Un scénario ne repart que d'un snapshot de calcul qui existe ; le lien recopié au gel est figé (ADR-0014) | Clés étrangères `derived_from` vers `calculation_snapshot` ; déclencheur `calculation_snapshot_only_name_changes` (0005) |
| **Acyclicité** | ❌ Impossible en déclaratif — tri topologique au chargement |
| **Racine unique** | ❌ Contrôle au chargement |
| **Aucun orphelin** | ❌ Contrôle au chargement |

Les trois dernières lignes sont la raison d'être de `bom_version.validated_at` : tant qu'il est
`NULL`, l'application refuse tout calcul sur cette version.

## Contrôle des garanties

Le tableau ci-dessus est vérifié, pas affirmé :

```bash
docker compose exec -T db psql -U 3istor -d 3istor -q < backend/migrations/checks/contraintes.sql
```

Vingt-six écritures interdites, chacune annoncée « refusé » avec la
contrainte qui l'a arrêtée — dont les six qui protègent une version validée
(ADR-0013) et les cinq qui protègent un snapshot de calcul (ADR-0014) : colonne
figée modifiée, suppression, nom en double dans la version, scénario porteur
supprimé, scénario reparti d'un snapshot inexistant. Sont aussi montrés acceptés : deux paramètres valides, dont une portée
pièce et une portée chemin sur la même pièce, le cas de précédence de
l'ADR-0002, et le renommage d'un snapshot de calcul. Un `WARNING` dans la sortie
signale une contrainte qui ne tient plus.

Exécuté sur Postgres 16.15 le 2026-10-01, sur la base locale et sur une base
neuve : 26 refus, 0 WARNING (après la migration 0005).

## Chargement du jeu de données

Le chargeur **n'ouvre pas de connexion** : il émet le script que `psql` exécute,
et il ne l'émet que si le jeu de données passe tous ses contrôles.

```bash
docker compose up -d
PYTHONPATH=backend/src python3 -m carcost.infrastructure seeds \
  | docker compose exec -T db psql -U 3istor -d 3istor -v ON_ERROR_STOP=1 -q
```

Contrôlé avant émission : acyclicité par tri topologique, racine unique, aucun
orphelin, valorisation exclusive, et **les quantités cumulées recalculées** puis
comparées à celles annoncées par le fichier. Un refus n'écrit rien du tout.

`validated_at` n'est renseigné qu'à la dernière instruction de la transaction :
une version présente en base mais non validée n'a pas passé les contrôles, et
l'application refuse de calculer dessus.

Chargé sur Postgres 16.15 le 2026-09-23 : 474 pièces, 689 arêtes, 302 achetées,
20 fournisseurs, 30 usines, 742 offres, 1 version validée.
