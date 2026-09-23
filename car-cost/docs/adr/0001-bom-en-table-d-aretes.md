# ADR-0001 — La nomenclature est stockée comme un graphe orienté acyclique, en table d'arêtes

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor — décision issue de la validation du cadrage du 2026-09-22

## Contexte et problème

La nomenclature de la Multipla n'est pas un arbre : la vis M6 est montée sous le moteur *et* sous la
carrosserie, une porte avant est montée deux fois, un siège plusieurs fois. Il faut choisir **comment
la stocker**, et ce choix commande tout le reste : la justesse des quantités cumulées, la possibilité
de répondre à « où est montée cette pièce ? », et la mise à jour d'un prix.

Contraintes : Postgres imposé ; BOM figée, chargée par un seed, en lecture seule dans l'outil
(hors périmètre §2.4) ; ordre de grandeur visé ≈ 350–500 pièces et 900–1300 arêtes.

## Critères de décision

1. **Fidélité au domaine** : une pièce doit pouvoir avoir plusieurs parents. *Critère décisif.*
2. Justesse des quantités cumulées (somme sur tous les chemins).
3. Coût des deux requêtes de l'écran : enfants directs d'un nœud, et where-used d'une pièce.
4. Possibilité de garantir l'acyclicité.
5. Simplicité pour une équipe de 4 en quelques semaines.

## Options envisagées

### Option A — Table d'arêtes
Deux tables : `part` (une ligne par pièce) et `bom_edge (parent_ref, child_ref, quantity, unit)`,
avec unicité sur (parent, enfant). Le graphe est explicite.
*Apporte* : multi-parents natif, une seule ligne par pièce, where-used = un `SELECT` sur la colonne
enfant. *Coûte* : toute lecture hiérarchique demande une récursion (CTE) ou un parcours applicatif ;
rien dans Postgres n'empêche un cycle.

### Option B — Colonne `parent_id` sur la pièce
Chaque pièce porte l'identifiant de son parent.
*Apporte* : le modèle le plus simple, supporté nativement par tous les ORM, requêtes récursives de
manuel. *Coûte* : une pièce ne peut avoir qu'un parent.

### Option C — Nomenclature éclatée à plat (une ligne par emplacement)
Ce que fait le classeur Excel actuel : une ligne par occurrence, avec la référence répétée.
*Apporte* : lecture directe sans jointure récursive, migration triviale depuis l'existant.
*Coûte* : la pièce n'existe plus en un seul exemplaire.

### Option D — Table d'arêtes **plus** table de fermeture transitive (closure table)
L'option A, augmentée d'une table dérivée contenant tous les couples (ancêtre, descendant).
*Apporte* : where-used et quantités cumulées en une requête, sans récursion.
*Coûte* : une table dérivée à maintenir cohérente, et ~10 à 50 fois plus de lignes.

## Décision

**Option A.** Raison décisive : une colonne `parent_id` ne rend pas la vis partagée coûteuse, elle la
rend **impossible à représenter**. Ce n'est pas un arbitrage de performance, c'est une perte
d'information sur le domaine.

L'acyclicité, que le modèle ne garantit pas seule, est vérifiée **explicitement** par tri topologique
au chargement, et toute écriture future devra la revérifier.

## Hypothèses et options abandonnées

**Option B — `parent_id`**
- *Ce qu'elle proposait* : un parent par pièce, hiérarchie triviale.
- *Pourquoi elle était séduisante* : c'est la solution par défaut de tout ORM et de tout tutoriel ;
  elle aurait divisé par deux le code de lecture et supprimé toute question d'acyclicité (un arbre
  ne peut pas boucler).
- *Ce qui l'a disqualifiée* : le jeu de données exige ≥ 40 pièces à parents multiples. Les
  représenter demanderait de dupliquer la pièce, donc de dupliquer son prix — et de le modifier à
  douze endroits pour changer un fournisseur.
- *Ce qui nous y ferait revenir* : rien de prévisible. Il faudrait que la nomenclature devienne
  réellement un arbre.

**Option C — nomenclature à plat**
- *Ce qu'elle proposait* : une ligne par emplacement, comme le classeur actuel.
- *Pourquoi elle était séduisante* : c'est le format d'entrée probable d'un export industriel, les
  lectures sont directes, et l'affichage de l'arbre ne demande aucune récursion.
- *Ce qui l'a disqualifiée* : elle reproduit exactement la maladie qu'on vient soigner. Le where-used
  devient une recherche textuelle, et une pièce n'a plus d'existence propre à laquelle rattacher un
  fournisseur ou un prix.
- *Ce qui nous y ferait revenir* : si l'outil se réduisait à afficher, en lecture seule, un export
  déjà éclaté par un système tiers.

**Option D — closure table dès maintenant**
- *Ce qu'elle proposait* : précalculer tous les couples ancêtre/descendant.
- *Pourquoi elle était séduisante* : elle rend le where-used et les quantités cumulées immédiats,
  sans récursion ni parcours applicatif — précisément les deux requêtes de l'écran principal.
- *Ce qui l'a disqualifiée* : c'est une optimisation sans mesure. Sur ~1200 arêtes, le parcours
  applicatif se compte en millisecondes, et la table dérivée devrait être reconstruite à chaque
  changement de BOM.
- *Ce qui nous y ferait revenir* : un where-used ou un dépliage mesuré au-delà de **200 ms** sur la
  BOM réelle, ou une BOM devenue éditable dans l'outil.

**Hypothèses de travail**
- La BOM est figée et en lecture seule : le seed est la source de vérité. *Risque* : si l'édition
  devient nécessaire, il faudra une vérification d'acyclicité transactionnelle à chaque écriture,
  ce qui n'est pas prévu.
- Le volume reste de l'ordre du millier d'arêtes. *Risque* : une BOM décuplée invaliderait le rejet
  de l'option D.

## Conséquences

**Positives**
- Le multi-parents est natif ; les ≥ 40 pièces partagées ne demandent aucun contournement.
- Une pièce = une ligne = un prix = un fournisseur : changer un paramètre se fait à un seul endroit.
- Le where-used est une requête directe sur la colonne enfant.

**Négatives**
- Toute lecture hiérarchique demande une récursion SQL ou un parcours applicatif ; il n'y a pas de
  « SELECT l'arbre ».
- L'acyclicité n'est **pas** garantie par le schéma : elle doit être contrôlée, et ce contrôle peut
  être oublié.
- Les outils et recettes habituels pour les arbres (chemins matérialisés, `ltree`) ne s'appliquent
  pas directement.

**Dette acceptée**
- Pas de table de fermeture, pas de cache de quantités cumulées en base. On y reviendra si le
  seuil des 200 ms est franchi.

## Comment on saura qu'on s'est trompé

Un dépliage de nœud ou un where-used qui dépasse 200 ms sur la BOM réelle, ou le besoin de dupliquer
une pièce pour représenter une situation de montage — signe que le modèle ne suffit plus.
