# Décisions d'architecture (ADR)

Un fichier par décision, numéroté, **immuable**. Si une décision change, on écrit un nouvel ADR et on
passe l'ancien en « remplacé par ADR-NNNN » : l'ancien reste lisible, avec son raisonnement d'époque.

Un ADR s'écrit **au moment de la décision**. Rédigé après le code, il devient une justification, et
ça se voit.

## Quand en écrire un

Dès qu'une décision remplit **au moins deux** de ces critères : coûteuse à défaire · une personne
raisonnable aurait pu choisir autrement · elle contraint d'autres décisions · quelqu'un demandera
dans trois mois « pourquoi avoir fait comme ça ? ».

Pas d'ADR pour un nom de variable ou le choix d'un linter.

## Index

| N° | Décision | Statut |
|---|---|---|
| [0001](0001-bom-en-table-d-aretes.md) | La nomenclature est un DAG stocké en table d'arêtes | accepté |
| [0002](0002-portee-des-parametres-piece-ou-chemin.md) | Un paramètre porte une portée explicite : pièce ou chemin | accepté |
| [0003](0003-snapshot-de-prix-persiste-et-immuable.md) | Le snapshot de prix est persisté, immuable et daté | accepté |
| [0004](0004-trois-couches-et-regle-de-dependance.md) | Trois couches, dépendances vers le domaine, vérifiées par un test | accepté |
| [0005](0005-calcul-par-programmation-dynamique-en-ordre-topologique.md) | Programmation dynamique en ordre topologique, une évaluation par pièce | accepté |
| [0006](0006-registre-de-regles-de-cout.md) | Registre de règles de coût ; une seule en v1 : `labour` | accepté |
| [0007](0007-sql-lit-le-graphe-le-code-calcule.md) | SQL lit le graphe, le code applicatif calcule | accepté |
| [0008](0008-mode-de-valorisation-exclusif.md) | Mode de valorisation exclusif : achetée ou fabriquée | accepté |
| [0009](0009-depliage-paresseux-du-dag-a-l-ecran.md) | Dépliage nœud par nœud, pièce partagée répétée et badgée | accepté |
| [0010](0010-prix-decompose-fournisseur-et-usine.md) | Prix = référence × multiplicateur fournisseur × coefficient d'usine | accepté |
| [0011](0011-decimal-exact-et-arrondi-a-l-affichage.md) | Décimal exact ; l'arrondi est un acte d'affichage | accepté |
| [0012](0012-comparaison-et-recommandation-par-piece.md) | Comparer sur un snapshot commun ; recommander le sourcing pièce par pièce | proposé |
| [0013](0013-version-de-nomenclature-validee-immuable.md) | Une version de nomenclature validée est immuable, et se garde en mémoire | proposé |
| [0014](0014-simulation-locale-prix-valhalla.md) | Simulation locale des prix Valhalla, indépendante des snapshots | proposé |

## Ce qui reste à décider

| Sujet | Déclencheur de l'ADR |
|---|---|
| Politique de prise de snapshot (manuelle, planifiée, à la demande) | Si la prise manuelle laisse l'utilisateur en `STALE` permanent (ADR-0003) |
| Make or buy (devis attaché à un nœud fabriqué) | À la première demande réelle (ADR-0008) |
