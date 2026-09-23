# ADR-0005 — Le coût est calculé par programmation dynamique, en ordre topologique, une évaluation par pièce

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor

## Contexte et problème

Sur un graphe où une pièce a plusieurs parents, la formule naturelle « un ensemble coûte la somme de
ses parties » se transforme, si on l'applique récursivement sans précaution, en une exploration de
**tous les chemins**. Le nombre de chemins d'un DAG croît multiplicativement : une vis employée sous
dix sous-ensembles, dont deux montés en double, est atteinte par bien plus de chemins qu'il n'y a de
pièces.

Il faut décider comment le moteur parcourt le graphe, et garantir que la garantie « une pièce n'est
évaluée qu'une fois » est vérifiable, pas espérée.

## Critères de décision

1. **Justesse sur les pièces partagées** : quantités cumulées sommées sur tous les chemins.
   *Décisif.*
2. Complexité linéaire en nœuds + arêtes.
3. Capacité à produire les **deux vues** (agrégée et par occurrence) et l'explication.
4. Lisibilité du code pour quatre personnes.

## Options envisagées

### Option A — Récursion naïve descendante
`coût(n) = Σ quantité(arête) × coût(enfant)`, appelée telle quelle.
*Apporte* : dix lignes, exactement la formule du domaine.
*Coûte* : le nombre d'appels est le nombre de chemins.

### Option B — Récursion avec mémoïsation (descendante)
La même récursion, avec un cache par pièce.
*Apporte* : garde la formulation naturelle, corrige le coût : une évaluation par pièce.
*Coûte* : profondeur de récursion, et l'ordre d'évaluation reste implicite.

### Option C — Tri topologique puis évaluation itérative ascendante
Un tri topologique ordonne les pièces ; on évalue les coûts unitaires des enfants vers les parents,
puis les quantités cumulées des parents vers les enfants sur l'ordre inverse.
*Apporte* : linéaire, sans récursion, et l'ordre d'évaluation est **matérialisé**.
*Coûte* : deux parcours à maintenir, et la formule du domaine se lit en deux temps.

### Option D — Calcul en SQL récursif
Traité séparément dans l'ADR-0007.

## Décision

**Option C**, dont l'option B est une conséquence : chaque pièce est évaluée exactement une fois.

Raison décisive : **le tri topologique est de toute façon obligatoire** pour prouver l'acyclicité
(invariant I3). Une fois qu'on l'a en main, l'évaluation itérative est gratuite, linéaire, sans
limite de récursion, et elle donne l'ordre d'évaluation exact — que l'explication peut afficher.

Mécanique retenue :
- **coûts unitaires** : parcours ascendant (enfants avant parents) ;
- **quantités cumulées** : parcours descendant sur l'ordre inverse, `q(enfant) += q(parent) × quantité d'arête` ;
- **vue agrégée** : contribution = quantité cumulée × coût unitaire, une ligne par pièce ;
- **vue par occurrence** : énumération des chemins, **à la demande et bornée à un sous-arbre** — elle
  n'est jamais calculée en entier pour le véhicule ;
- **garantie testée** : un compteur d'appels prouve que la pièce partagée du DAG en losange est
  évaluée une seule fois. Ce test est écrit **avant** le moteur.

## Hypothèses et options abandonnées

**Option A — récursion naïve**
- *Ce qu'elle proposait* : la formule du domaine, écrite littéralement.
- *Pourquoi elle était séduisante* : c'est le code le plus court et le plus lisible du projet ; il se
  relit en dix secondes et correspond mot pour mot à l'énoncé métier. Sur un arbre, c'est la bonne
  réponse.
- *Ce qui l'a disqualifiée* : le nombre d'appels est le nombre de chemins, pas le nombre de pièces.
  Le partage, qui est le fait central de cette nomenclature, la rend impraticable — et, pire, elle
  reste **juste** tout en étant lente, donc l'erreur ne se voit pas sur un petit jeu de données.
- *Ce qui nous y ferait revenir* : jamais sur cette nomenclature.

**Option B — récursion mémoïsée**
- *Ce qu'elle proposait* : la même récursion, avec un cache.
- *Pourquoi elle était séduisante* : elle conserve la lisibilité de A **et** la complexité de C, pour
  une ligne de code de plus. C'est une option parfaitement défendable, et nous en gardons la
  propriété centrale (une évaluation par pièce).
- *Ce qui l'a disqualifiée* : deux points mineurs mais réels — la profondeur de récursion Python sur
  un graphe à plus de cinq niveaux avec chaînage matière, et surtout l'**ordre d'évaluation non
  matérialisé**, alors que l'explication doit pouvoir montrer dans quel ordre les coûts se sont
  agrégés. Le tri topologique étant déjà nécessaire, C ne coûte rien de plus.
- *Ce qui nous y ferait revenir* : si le calcul devait devenir **paresseux** — n'évaluer qu'un
  sous-arbre à la demande, par exemple pour un dépliage très profond. La forme descendante est alors
  la bonne.

**Hypothèses de travail**
- Ordre de grandeur : ~350–500 pièces, ~900–1300 arêtes, profondeur ≥ 5 ⇒ calcul complet de l'ordre
  de quelques millisecondes. *Risque* : non mesuré à ce stade ; le seuil de réaction est fixé à 2 s
  (périmètre §3.4).
- La vue par occurrence n'est jamais demandée pour le véhicule entier. *Risque* : si elle l'était,
  le volume de lignes serait celui du nombre de chemins ; il faudrait paginer ou refuser.

## Conséquences

**Positives**
- Complexité linéaire, garantie par un test à compteur d'appels et non par une intention.
- L'ordre d'évaluation est une donnée : l'explication peut montrer comment le total s'est construit.
- Pas de limite de récursion, quelle que soit la profondeur.

**Négatives**
- Deux parcours de sens opposés à maintenir : une erreur de sens produit des quantités fausses de
  façon plausible (et donc difficile à repérer à l'œil).
- La formule du domaine ne se lit plus en un seul endroit.
- La vue par occurrence reste un objet potentiellement volumineux, à borner explicitement.

**Dette acceptée**
- Aucun calcul paresseux par sous-arbre, aucun parallélisme, aucun recalcul incrémental : chaque
  recalcul refait tout le graphe.

## Comment on saura qu'on s'est trompé

Le compteur d'appels montre plus d'une évaluation par pièce ; ou un profilage montre que le tri
topologique domine le temps de calcul ; ou la vue par occurrence ne tient pas en mémoire sur la BOM
réelle.
