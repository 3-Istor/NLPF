# ADR-0007 — SQL lit le graphe, le code applicatif calcule le coût

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor

## Contexte et problème

Postgres sait parcourir un graphe : une CTE récursive calcule quantités cumulées et coûts en une
requête, au plus près des données. La tentation est réelle, et l'argument de performance est bon.

Il faut donc décider ce que fait la base et ce que fait le code — sachant que l'écran principal a
besoin de deux requêtes fondamentalement ensemblistes (les enfants directs d'un nœud, le where-used
d'une pièce) et que le calcul, lui, porte des règles métier.

## Critères de décision

1. **Respect de la règle de dépendance** (ADR-0004) : le domaine n'importe rien de l'infrastructure,
   donc aucune règle métier ne peut vivre dans une requête. *Décisif.*
2. Testabilité : le moteur doit se tester sans base.
3. Performance réelle, mesurée, pas supposée.
4. Compétence de l'équipe et lisibilité pour un arrivant.

## Options envisagées

### Option A — Tout en SQL
Une CTE récursive parcourt le graphe, multiplie les quantités, applique les prix et agrège.
*Apporte* : une seule requête, exécution près des données, aucun transfert de 1200 arêtes,
performances excellentes.
*Coûte* : le mode de valorisation, les règles, les surcharges de scénario et l'explication deviennent
du SQL.

### Option B — Tout en applicatif
La base ne sert qu'à stocker : `SELECT *` sur les pièces et les arêtes, tout le reste en Python.
*Apporte* : un seul endroit où penser, un seul langage.
*Coûte* : le dépliage nœud par nœud et le where-used paginé obligeraient à charger le graphe entier —
ce que l'écran interdit explicitement.

### Option C — Hybride, avec une frontière nommée
SQL fait les **lectures ensemblistes** : enfants directs, where-used, recherche, pagination, compte
de parents. Python fait le **calcul** : valorisation, règles, quantités cumulées, contributions,
explication.
*Apporte* : chacun son métier ; le moteur reste testable sans base.
*Coûte* : deux endroits parlent du graphe.

## Décision

**Option C**, énoncée comme une règle simple et vérifiable en revue : **aucune règle métier dans une
requête SQL, aucun parcours de graphe complet en Python pour un besoin d'affichage.**

Raison décisive : une règle de coût exprimée en SQL n'est testable qu'avec une base, ne peut pas être
une stratégie enregistrée (ADR-0006), et viole la règle de dépendance. À l'inverse, paginer les
enfants d'un nœud est exactement ce que la base fait bien.

## Hypothèses et options abandonnées

**Option A — tout en SQL**
- *Ce qu'elle proposait* : le calcul complet en une CTE récursive.
- *Pourquoi elle était séduisante* : c'est la solution la plus performante, et de loin — rien ne
  transite sur le réseau, l'agrégation se fait là où sont les données, et sur une nomenclature qui
  grossirait, elle resterait tenable là où le chargement applicatif ne le serait plus. Techniquement,
  c'est la plus élégante des trois.
- *Ce qui l'a disqualifiée* : elle place le cœur métier — mode de valorisation, portée des
  paramètres, règles actives — dans un langage où il n'est ni testable sans base, ni lisible pour
  l'équipe, ni extensible par un registre de stratégies. Et le projet interdit explicitement de
  mettre de la règle métier dans une requête.
- *Ce qui nous y ferait revenir* : une BOM de plusieurs centaines de milliers d'arêtes, où le seul
  transfert des données dominerait le temps de calcul.

**Option B — tout en applicatif**
- *Ce qu'elle proposait* : la base comme simple entrepôt.
- *Pourquoi elle était séduisante* : un seul langage, un seul modèle mental, aucune requête à écrire
  au-delà du trivial ; toute la logique se teste en mémoire, et l'équipe n'a pas à monter en
  compétence sur les CTE récursives.
- *Ce qui l'a disqualifiée* : le dépliage nœud par nœud exige de ne charger **que** les enfants
  directs. Les filtrer en Python supposerait d'avoir déjà tout chargé — exactement l'anti-pattern que
  l'écran proscrit.
- *Ce qui nous y ferait revenir* : non ; c'est la frontière, pas le principe, qui est en jeu.

**Hypothèses de travail**
- Charger ~350 pièces et ~1300 arêtes pour un calcul complet coûte moins de 50 ms. *Risque* : non
  mesuré ; si le chargement dépasse le calcul lui-même, la frontière est mal placée.
- Les requêtes de lecture restent **descriptives** (filtrer, joindre, compter, paginer) et ne
  contiennent jamais de prix ni de multiplication de quantités. C'est un point de revue explicite.

## Conséquences

**Positives**
- Le moteur se teste sans base, sur des fixtures en mémoire.
- Les requêtes de lecture sont simples, indexables et optimisables indépendamment.
- Le dépliage ne charge jamais plus que ce que l'écran affiche.

**Négatives**
- Le graphe est chargé en mémoire à chaque calcul complet : pas de recalcul incrémental.
- Deux endroits parlent du graphe (requêtes de lecture et moteur) ; ils doivent rester cohérents sur
  la notion d'arête.
- On renonce volontairement à un gain de performance disponible.

**Dette acceptée**
- Recalcul complet systématique, sans réutilisation entre deux calculs voisins. Réouverture prévue si
  le recalcul dépasse 2 s (périmètre §3.4).

## Comment on saura qu'on s'est trompé

Le chargement du graphe dépasse durablement le temps de calcul lui-même ; ou une revue trouve un prix
ou une multiplication de quantités dans une requête SQL — signe que la frontière a bougé sans qu'on
le décide.
