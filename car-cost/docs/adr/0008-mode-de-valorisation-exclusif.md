# ADR-0008 — Chaque pièce porte un mode de valorisation exclusif : achetée (feuille, avec prix) ou fabriquée (somme des enfants, sans prix)

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor

## Contexte et problème

La faute la plus coûteuse d'un outil de chiffrage sur nomenclature est la **double comptabilisation** :
compter le prix d'achat d'un ensemble *et* le coût de ses composants. L'erreur est silencieuse — le
total reste plausible — et elle se propage à toutes les décisions prises ensuite. Son symétrique est
tout aussi grave : un ensemble dont on cherche un prix qui n'existe pas et qui vaut alors zéro.

Il faut décider comment une pièce obtient son coût, et à quel moment cette règle est vérifiée.

## Critères de décision

1. **Rendre la double comptabilisation impossible**, pas seulement improbable. *Décisif.*
2. Vérifiabilité mécanique à la génération du jeu de données et à l'import.
3. Simplicité du moteur : le moins de cas possible.
4. Réalisme industriel.

## Options envisagées

### Option A — Exclusivité stricte
`purchased` ⇒ **aucune arête sortante** et prix obligatoire dans le catalogue.
`manufactured` ⇒ **au moins un enfant** et **aucun prix propre**.
Les deux règles sont vérifiées à la génération, qui refuse le fichier, puis à l'import.
*Apporte* : l'erreur devient structurellement impossible ; le moteur a deux cas.
*Coûte* : on ne peut pas décrire un ensemble acheté dont on connaît la composition.

### Option B — Mode mixte autorisé
Un nœud peut avoir un prix **et** des enfants, avec un drapeau indiquant lequel prime.
*Apporte* : couvre le cas industriel de la sous-traitance d'un ensemble dont on connaît le contenu.
*Coûte* : la justesse repose sur un drapeau qu'on peut oublier de lire.

### Option C — Déduction implicite
Pas de mode : on prend le prix s'il existe, sinon on somme les enfants.
*Apporte* : aucun champ à saisir, aucun contrôle à écrire.
*Coûte* : un prix qui traîne dans le catalogue change silencieusement le sens d'un nœud.

## Décision

**Option A.** Raison décisive : c'est la seule option où la double comptabilisation est **impossible
par construction**, et non évitée par une règle de priorité qu'un développeur pressé peut ignorer.
Le contrôle vit dans le générateur et dans l'import : une donnée non conforme **ne rentre pas**.

Côté moteur, cela se traduit par deux interdits symétriques, chacun couvert par un test :
- sur un nœud acheté, **ne jamais sommer les enfants** (il n'en a pas) ;
- sur un nœud fabriqué, **ne jamais chercher un prix** dans le snapshot.

## Hypothèses et options abandonnées

**Option B — mode mixte**
- *Ce qu'elle proposait* : un nœud à la fois acheté et décomposé, avec un drapeau de priorité.
- *Pourquoi elle était séduisante* : elle décrit une situation industrielle parfaitement réelle. On
  sous-traite un ensemble, on en connaît quand même la composition, et l'on veut pouvoir comparer
  « acheté » et « fabriqué » sur le **même** nœud — ce qui est exactement une question d'aide à la
  décision (*make or buy*), donc dans l'esprit de l'outil.
- *Ce qui l'a disqualifiée* : elle réintroduit précisément le risque que la décision vise à
  supprimer. La justesse du total dépendrait d'un drapeau lu au bon endroit ; son oubli donnerait un
  total faux **et plausible**. Et aucune des cinq questions métier retenues au cadrage ne demande le
  *make or buy*.
- *Ce qui nous y ferait revenir* : la première fois que la question « vaut-il mieux acheter ou
  fabriquer ce sous-ensemble ? » est posée pour de bon. Ce sera alors un nouvel ADR, pas une rustine
  — piste à explorer : un **devis attaché** à un nœud fabriqué, affiché à côté du coût calculé et
  jamais sommé avec lui.

**Option C — déduction implicite**
- *Ce qu'elle proposait* : déduire le comportement de la présence d'un prix.
- *Pourquoi elle était séduisante* : zéro champ, zéro contrôle, zéro documentation ; le jeu de
  données s'écrit plus vite et le moteur tient en moins de lignes.
- *Ce qui l'a disqualifiée* : le sens d'un nœud dépendrait alors d'un fait extérieur — la présence
  d'une ligne dans un catalogue de prix. Un prix hérité d'un ancien import suffirait à faire
  disparaître tout le contenu d'un ensemble du total, sans qu'aucun contrôle ne le signale.
- *Ce qui nous y ferait revenir* : jamais. C'est de l'implicite là où le domaine demande de
  l'explicite.

**Hypothèses de travail**
- Toute pièce achetée a un prix dans le catalogue ; son absence est une panne (P3), pas un mode de
  valorisation. *Risque* : aucun, tant que la validation du jeu de données tient.
- Les matières premières et la visserie sont des pièces `purchased`, donc des feuilles. *Risque* :
  si l'on voulait un jour décomposer une matière (minerai → lingot → tôle), il faudrait la
  reclasser en `manufactured`, ce qui changerait son mode et son prix.

## Conséquences

**Positives**
- La double comptabilisation est impossible ; l'invariant I2 est tenu par la structure des données.
- La validation est mécanique et précoce : le générateur refuse le fichier, l'import refuse la
  ligne.
- Le moteur se réduit à deux cas exhaustifs, donc à deux branches testées.

**Négatives**
- Un ensemble sous-traité dont on connaît la composition n'est pas représentable.
- « Ouvrir » plus tard une pièce achetée (lui donner des composants) impose de changer son mode,
  donc de retirer son prix — ce n'est pas une simple addition de données.
- Le jeu de données doit être rigoureux sur la frontière achat/fabrication, y compris pour des
  pièces où elle est discutable (un faisceau électrique, un siège complet).

**Dette acceptée**
- Pas de *make or buy*, pas de devis attaché, pas de coût cible.

## Comment on saura qu'on s'est trompé

Une pièce de la nomenclature réelle exige d'être les deux à la fois, ou un utilisateur demande le
coût d'un ensemble sous-traité — signe que l'exclusivité stricte a coupé trop court.
