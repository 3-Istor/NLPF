# ADR-0009 — L'arbre se déplie nœud par nœud côté serveur ; une pièce partagée est répétée et porte son compte d'emplois

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor

## Contexte et problème

L'écran principal doit laisser naviguer du véhicule complet jusqu'à une vis. La nomenclature compte
plus de 350 pièces et plus d'un millier d'arêtes, et elle est un **graphe** : une pièce partagée sera
rencontrée à plusieurs endroits de l'arborescence.

Deux questions se posent ensemble, parce que la réponse à l'une contraint l'autre : **que charge-t-on
et quand**, et **comment montre-t-on qu'une même pièce apparaît à plusieurs endroits sans que
l'utilisateur croie à un doublon de données** ?

## Critères de décision

1. **Le navigateur ne monte jamais le graphe entier.** Exigence explicite. *Décisive.*
2. L'utilisateur ne doit pas prendre une répétition pour une erreur de données.
3. Coût réseau et latence ressentie au dépliage.
4. Simplicité du front : il affiche, il ne calcule pas.

## Options envisagées

### Option A — Chargement complet au premier affichage
Le front reçoit pièces et arêtes, construit l'arborescence et déplie localement.
*Apporte* : dépliage instantané, recherche et surlignage triviaux, un seul appel, aucun état de
chargement à gérer.
*Coûte* : le front possède le graphe — et finira par calculer dessus.

### Option B — Dépliage paresseux, nœud par nœud
`GET /nodes/{path}/children` renvoie les **enfants directs** d'une occurrence, chacun avec : quantité
d'arête et unité, mode de valorisation, coût unitaire, contribution, `has_children`, et
`parent_count` (le nombre d'emplois de la pièce dans le véhicule). Une pièce partagée apparaît à
**chaque** emplacement, avec un badge « utilisée à N endroits » menant à la vue where-used.
*Apporte* : mémoire bornée, et le front ne peut pas recalculer ce qu'il n'a pas.
*Coûte* : un aller-retour par dépliage.

### Option C — Dépliage paresseux avec pré-chargement de N niveaux
Comme B, mais chaque appel ramène deux ou trois niveaux d'avance.
*Apporte* : moins d'allers-retours, dépliage plus fluide.
*Coûte* : une profondeur à régler et un cache à invalider après recalcul.

## Décision

**Option B.**

Raison décisive : l'exigence est explicite, et elle est **structurante plutôt que cosmétique** — un
front qui ne possède jamais le graphe ne peut pas se mettre à faire de l'arithmétique métier, donc
les deux vérités concurrentes (le total de l'API et le total recalculé à l'écran) ne peuvent pas
apparaître.

Représentation du graphe à l'écran :
- **l'identité d'une ligne de l'arbre est son chemin**, pas sa référence. Deux lignes de même
  référence sous deux parents différents sont deux occurrences distinctes, dépliables
  indépendamment ;
- une pièce partagée est **répétée** à chaque emplacement — c'est fidèle au montage réel ;
- elle porte un badge donnant le **compte exact** d'emplois, calculé côté serveur, et ce badge ouvre
  la vue *where-used* ;
- la recherche renvoie le **chemin** de chaque résultat, ce qui permet au front de déplier de proche
  en proche jusqu'à la pièce trouvée.

## Hypothèses et options abandonnées

**Option A — chargement complet**
- *Ce qu'elle proposait* : tout le graphe d'un coup, dépliage local.
- *Pourquoi elle était séduisante* : c'est de loin le front le plus simple et le plus agréable —
  dépliage instantané, recherche immédiate sans appel, aucun état de chargement, aucune gestion
  d'erreur par nœud. Sur une nomenclature de trente pièces, ce serait la bonne réponse, et il faut
  reconnaître ce qu'on perd : la fluidité.
- *Ce qui l'a disqualifiée* : l'exigence explicite, et une raison de fond — disposer du graphe côté
  client rend le recalcul local tentant, puis inévitable, et deux totaux finissent par diverger.
- *Ce qui nous y ferait revenir* : une nomenclature assez petite pour tenir dans une réponse, et
  aucune contrainte de calcul serveur. Pas ce projet.

**Option C — pré-chargement de N niveaux**
- *Ce qu'elle proposait* : le compromis entre A et B.
- *Pourquoi elle était séduisante* : elle supprime la latence perçue sur les premiers niveaux, qui
  sont ceux qu'on ouvre le plus souvent, sans jamais charger tout le graphe. C'est probablement ce
  qu'il faudra faire si le dépliage paraît lent.
- *Ce qui l'a disqualifiée* : elle ajoute un paramètre à régler et un cache à invalider après chaque
  recalcul, pour un gain **non mesuré**. On ne l'exclut pas, on la reporte.
- *Ce qui nous y ferait revenir* : un dépliage ressenti au-delà de **300 ms** ; on pré-chargerait
  alors deux niveaux.

**Hypothèses de travail**
- Un nœud a rarement plus d'une trentaine d'enfants directs. *Risque* : si un ensemble en a 200
  (une caisse en blanc, un faisceau), il faudra paginer les enfants — la route est conçue pour le
  permettre.
- Le badge « utilisée à N endroits » suffit à empêcher l'utilisateur d'interpréter la répétition
  comme un doublon. *Risque* : non vérifié auprès d'un utilisateur qui n'a pas construit l'outil ;
  c'est une hypothèse d'ergonomie, à tester.

## Conséquences

**Positives**
- Mémoire du navigateur bornée, quelle que soit la taille de la nomenclature.
- Le front reste un afficheur : aucun total ne peut y être recalculé.
- Le compte d'emplois et le where-used sont des données serveur, donc cohérents avec le calcul.

**Négatives**
- Un appel par dépliage : la latence réseau devient visible, et chaque nœud a son état de chargement
  et son état d'erreur.
- La recherche doit renvoyer des chemins, et le front déplier en cascade — plus complexe qu'un
  filtre local.
- Le marquage « modifié » d'un nœud et de toute sa remontée doit être connu **du serveur**, puisque
  le front ne connaît pas le graphe.

**Dette acceptée**
- Pas de pré-chargement, pas de cache au-delà des nœuds déjà ouverts, pas de pagination des enfants
  en v1 (la route la prévoit, l'implémentation viendra au premier nœud trop large).

## Comment on saura qu'on s'est trompé

Le nombre d'allers-retours pour atteindre une vis rend la navigation désagréable (> 300 ms ressentis
par dépliage) ; ou un utilisateur, badge sous les yeux, prend encore une pièce partagée pour un
doublon de données.
