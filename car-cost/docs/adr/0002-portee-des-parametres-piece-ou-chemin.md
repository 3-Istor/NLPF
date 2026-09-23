# ADR-0002 — Un paramètre de scénario porte une portée explicite : pièce ou chemin

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor — décision D3, validée le 2026-09-22

## Contexte et problème

Quand l'utilisateur règle « cette vis vient du fournisseur X », à quoi s'applique le réglage ? À
**toutes** les occurrences de la vis dans le véhicule (elle est montée à douze endroits), ou
seulement à celle qu'il regarde, sous le sous-ensemble où il se trouve ?

La question n'est pas cosmétique. Elle décide de la clé de mémoïsation du moteur, donc de sa
complexité ; et elle a une conséquence directe à l'écran, puisque l'interface doit dire à
l'utilisateur ce que son réglage affecte. Il faut la trancher **avant** d'écrire le modèle de
scénario.

## Critères de décision

1. **Ce que l'utilisateur peut exprimer, et comprendre.** L'interface doit pouvoir énoncer la portée
   sans mentir. *Critère décisif.*
2. Préservation de la mémoïsation : une pièce évaluée une seule fois (ADR-0005).
3. Lisibilité de l'explication : on doit savoir quelle surcharge s'est appliquée à quelle ligne.
4. Coût d'implémentation et de test.

## Options envisagées

### Option A — Portée « pièce » uniquement
Un paramètre s'applique à la référence, donc partout. Clé de mémoïsation : la référence.
*Apporte* : un seul chemin de code, mémoïsation triviale, explication simple.
*Coûte* : « ce moteur-là est sourcé à Turin, pas les autres » devient inexprimable.

### Option B — Portée « chemin » uniquement
Tout paramètre s'applique à une occurrence désignée par son chemin complet.
*Apporte* : modèle uniforme, aucune ambiguïté d'interprétation, granularité maximale.
*Coûte* : deux occurrences d'une même pièce ne partagent plus rien ; la mémoïsation par pièce
disparaît.

### Option C — Les deux, portée explicite sur chaque paramètre, « pièce » par défaut
Chaque paramètre porte un champ `scope` valant `part` ou `path`. La clé de mémoïsation devient
`(pièce, contexte)`, où le contexte est l'ensemble des surcharges de chemin actives applicables à la
branche parcourue. **Sans aucune surcharge de chemin, le contexte est vide et le comportement est
exactement celui de l'option A.**
*Apporte* : les deux besoins métier, avec une dégradation proportionnelle à l'usage.
*Coûte* : deux chemins de résolution à écrire et à tester, une clé de mémoïsation non triviale.

## Décision

**Option C**, conformément à la décision D3, avec **`part` comme valeur par défaut**.

Raison décisive : la portée pièce seule rend inexprimable un besoin d'acheteur réel ; la portée
chemin seule fait payer à l'ensemble du graphe le prix d'un cas minoritaire. L'option C est la seule
où **le coût du calcul est proportionnel à l'usage réel de la portée fine** : tant qu'aucune
surcharge de chemin n'est posée, le nombre d'entrées mémoïsées est exactement le nombre de pièces.

Borne annoncée : le nombre d'entrées mémoïsées est majoré par
`nombre de pièces × (1 + nombre de sous-arbres sous surcharge de chemin)`.

## Hypothèses et options abandonnées

**Option A — portée pièce uniquement**
- *Ce qu'elle proposait* : un paramètre = une référence, appliqué partout.
- *Pourquoi elle était séduisante* : clé de mémoïsation triviale, un seul jeu de tests, explication
  immédiatement lisible, et aucune question d'interface à résoudre — le message serait toujours le
  même. C'est la conception la plus simple qui reste correcte.
- *Ce qui l'a disqualifiée* : le besoin « ce sous-ensemble-là est sourcé ailleurs » est un cas
  d'usage d'acheteur courant, et le rendre impossible aurait fermé la question métier Q3.
- *Ce qui nous y ferait revenir* : mesure, après la tranche T2 : si aucun scénario enregistré ne
  contient de surcharge de chemin, la portée fine est du code mort et doit être retirée.

**Option B — portée chemin uniquement**
- *Ce qu'elle proposait* : tout paramètre désigne une occurrence.
- *Pourquoi elle était séduisante* : un seul concept au lieu de deux, aucune ambiguïté possible pour
  l'utilisateur, et la granularité maximale — chaque emplacement de montage réglable indépendamment,
  ce qui est la réalité d'un atelier.
- *Ce qui l'a disqualifiée* : le nombre de chemins d'un DAG croît multiplicativement (une vis
  employée sous des sous-ensembles eux-mêmes montés en plusieurs exemplaires). Régler une vis
  « partout » demanderait de poser douze paramètres, et le moteur perdrait sa propriété d'évaluation
  unique par pièce.
- *Ce qui nous y ferait revenir* : si la nomenclature devenait un arbre — auquel cas chemin et pièce
  coïncideraient.

**Hypothèses de travail**
- Les surcharges de chemin restent **rares** : quelques-unes par scénario. *Risque* : un scénario en
  contenant des centaines ferait exploser le nombre d'entrées mémoïsées ; il faudra alors mesurer et,
  le cas échéant, plafonner.
- L'utilisateur comprend la distinction si l'interface la nomme explicitement (« s'applique aux 12
  occurrences » contre « s'applique à cette occurrence »). *Risque* : non vérifié ; à tester auprès
  d'un utilisateur qui n'a pas construit l'outil.

## Conséquences

**Positives**
- Les deux besoins métier sont exprimables, et l'écran peut dire la vérité sur ce qu'il fait.
- Le cas courant (portée pièce) ne paie rien pour le cas rare.
- La portée étant une donnée du scénario, elle est persistée, rejouable et explicable.

**Négatives**
- Deux chemins de résolution à maintenir et à tester, y compris leur interaction (une surcharge
  pièce et une surcharge chemin sur la même pièce : **la plus spécifique gagne**, et l'explication
  doit le dire).
- La clé de mémoïsation n'est plus « la référence » : toute personne qui touche au moteur doit
  comprendre la notion de contexte.
- Le nombre d'entrées mémoïsées devient une grandeur à surveiller.

**Dette acceptée**
- La portée `path` n'est **résolue par le moteur et exposée à l'écran qu'en tranche T2**. En T1, le
  champ existe, est persisté, et vaut toujours `part`. Condition de sortie : fin de T2.

## Comment on saura qu'on s'est trompé

Sur un scénario réaliste, le nombre d'entrées mémoïsées dépasse le double du nombre de pièces — ou,
à l'inverse, personne n'utilise jamais la portée chemin : dans les deux cas, la décision était
mauvaise, en excès ou en défaut.
