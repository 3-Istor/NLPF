# ADR-0013 — Une version de nomenclature validée est immuable, et se garde en mémoire

- **Date** : 2026-09-28
- **Statut** : proposé
- **Décideurs** : équipe 3istor — à valider en revue de la PR qui l'introduit

## Contexte et problème

`bom_version.validated_at` atteste qu'un graphe a passé ses contrôles : acyclicité, racine unique,
aucun orphelin (ADR-0001, ADR-0008). Rien n'empêchait jusqu'ici de modifier ce graphe **après** :
ajouter une arête, changer une quantité, retoucher un multiplicateur fournisseur. L'attestation
portait alors sur un graphe qui n'existe plus, et un calcul enregistré sur cette version ne se
rejouait plus à l'identique.

Second problème, de performance cette fois : chaque requête relisait la version entière en base
(trois requêtes, une connexion neuve). Un dépliage coûtait une relecture de 474 pièces et 689 arêtes.
Un cache règle ce problème, mais un cache sans invalidation n'est juste que si la donnée ne change
pas.

Le périmètre écarte déjà le versionnement avec diff (perimetre.md §2, ligne 10) : « une version
figée suffit ». Il ne dit pas **qui** la fige.

## Critères de décision

1. **Reproductibilité** d'un calcul enregistré. *Décisif.*
2. Coût d'une lecture de nomenclature par requête.
3. Simplicité : pas d'invalidation de cache à coordonner entre processus.
4. Possibilité de corriger une nomenclature fausse.

## Options envisagées

### Option A — Version modifiable, cache invalidé à l'écriture
*Apporte* : corriger une quantité sur place.
*Coûte* : l'invalidation (un seul processus aujourd'hui, plusieurs demain), et la reproductibilité :
un calcul ancien pointe vers un graphe qui a changé sous lui.

### Option B — Version modifiable, aucun cache
*Apporte* : rien à invalider.
*Coûte* : la relecture par requête, et la reproductibilité n'est pas réglée.

### Option C — Version validée immuable, imposée par la base ; cache sans expiration
Une fois `validated_at` renseigné, la base refuse toute écriture sur `bom_version`, `part`,
`bom_edge` et `part_supplier` de cette version. Corriger, c'est charger une nouvelle version.
*Apporte* : reproductibilité par construction, cache trivialement juste.
*Coûte* : une correction coûte un rechargement complet sous un nouvel identifiant.

## Décision

**Option C.** Raison décisive : c'est la seule qui rende un calcul enregistré rejouable sans
dépendre de la discipline de celui qui écrit en base. Même logique que les snapshots de prix
(ADR-0003), même mécanisme : un déclencheur.

Règles retenues :
- le chargeur écrit pièces, arêtes et fournisseurs **avant** de renseigner `validated_at`, dans la
  même transaction : il n'est pas gêné ;
- tout chemin qui renseigne `validated_at` passe par `domain/bom_validation.py` ;
- l'API garde en mémoire chaque version lue avec succès, sans expiration. Une version inconnue ou non
  validée n'est **pas** mise en cache : elle peut le devenir pendant que le serveur tourne ;
- la liste des versions (`GET /bom/versions`) n'est jamais mise en cache.

## Hypothèses et options abandonnées

**Option A — version modifiable avec invalidation**
- *Pourquoi elle était séduisante* : corriger une quantité fausse en une requête.
- *Ce qui l'a disqualifiée* : la reproductibilité. Un calcul du lundi, relu le jeudi, afficherait
  ses montants à côté d'un graphe qui n'est plus celui qui les a produits.
- *Ce qui nous y ferait revenir* : l'édition de nomenclature à l'écran. Il faudrait alors une
  version **brouillon** modifiable, validée puis figée. Le brouillon serait une nouvelle version,
  jamais l'ancienne.

**Hypothèses de travail**
- Le nombre de versions chargées reste petit : le cache n'a pas de borne. *Risque* : une version
  pèse quelques centaines de kilo-octets, ce qui ne devient un problème qu'au-delà de centaines de
  versions.
- `supplier` et `supplier_plant` ne sont **pas** versionnées : un coefficient d'usine modifié change
  le prix des calculs futurs **et** fausserait l'explication d'un calcul ancien. *Risque* : connu et
  non couvert par cette décision. Le couvrir demande de versionner le sourcing.

## Conséquences

**Positives**
- Un dépliage ne touche plus la base après la première lecture de la version.
- `validated_at` dit enfin quelque chose de durable.
- Deux clients peuvent travailler sur deux versions sans rien partager d'autre que l'identifiant dans
  l'URL : l'API reste sans état.

**Négatives**
- Pour supprimer une version validée, il faut un superutilisateur qui désactive le déclencheur,
  ou repartir d'une base vide (`docker compose down -v`).
- Six écritures interdites de plus à contrôler : `checks/contraintes.sql` attend 21 refus au lieu
  de 15.
