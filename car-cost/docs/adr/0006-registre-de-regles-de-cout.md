# ADR-0006 — Les règles de coût sont des stratégies enregistrées dans un registre ; une seule en v1 : `labour`

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor — décision M2, validée le 2026-09-22 : « je veux que ce soit facile
  d'en rajouter ; pour l'instant seulement `labour` »

## Contexte et problème

Le coût unitaire d'un ensemble fabriqué est la somme de ses enfants, plus des modificateurs :
aujourd'hui la main-d'œuvre, demain peut-être autre chose. La demande est explicite : **l'ajout d'une
règle doit être facile**, et une seule règle existe pour l'instant.

Il y a une tension à nommer : le projet s'interdit les abstractions « au cas où ». Une fabrique de
stratégies pour une seule règle en est une — sauf que la facilité d'ajout est ici une **exigence
exprimée**, et que la liste des règles actives est de toute façon nécessaire à la reproductibilité
(un calcul doit enregistrer les versions de règles utilisées). C'est ce qui fait pencher.

## Critères de décision

1. **Coût d'ajout d'une nouvelle règle**, en fichiers touchés et en tests à refaire. *Décisif — c'est
   la demande.*
2. Reproductibilité : le calcul doit enregistrer **quelles** règles étaient actives et **dans quel
   ordre** elles se sont appliquées.
3. Ne pas payer aujourd'hui pour un besoin imaginaire.
4. Lisibilité de l'explication : une ligne de coût doit pouvoir dire quelle règle l'a modifiée.

## Options envisagées

### Option A — Conditions en dur dans le moteur
`if scenario.labour_enabled: cost += ...`, au fil du calcul.
*Apporte* : aucune indirection, le calcul se lit d'un bloc.
*Coûte* : ajouter une règle, c'est modifier le cœur du moteur et ses tests.

### Option B — Registre de stratégies
Une interface `CostRule` avec `name`, `applies_to(node)` et `apply(context) -> CostAdjustment` ; un
décorateur d'enregistrement ; un **ordre d'application déterministe et documenté**. Le scénario porte
la liste des règles actives, le calcul la persiste.
*Apporte* : ajouter une règle = un fichier + un test, sans toucher au moteur ; la liste des règles
devient une donnée du résultat.
*Coûte* : une indirection pour une seule règle aujourd'hui.

### Option C — Moteur de règles piloté par les données (DSL en base)
Les règles sont des expressions stockées, interprétées à l'exécution.
*Apporte* : on ajoute une règle sans redéployer ; un non-développeur pourrait en écrire.
*Coûte* : un langage à concevoir, tester, documenter et sécuriser.

## Décision

**Option B**, avec **une seule règle enregistrée en v1 : `labour`** (inclure ou exclure la
main-d'œuvre, ce qui permet de lire le coût matière seul).

Raison décisive : la demande porte sur la facilité d'ajout, et une interface à deux méthodes plus un
registre nommé la satisfont exactement — tout en produisant, gratuitement, la donnée dont
l'invariant de reproductibilité a besoin : la liste ordonnée des règles actives.

**Ce qui n'est pas une règle**, et ne doit pas le devenir : le multiplicateur fournisseur et le
coefficient d'usine (ADR-0010) sont des composantes du prix d'achat, pas des modificateurs
activables. Les rendre désactivables permettrait de produire un prix qui ne correspond à aucun achat
possible. Le taux horaire n'est pas une règle non plus : c'est une donnée du scénario, que la règle
`labour` consomme.

## Hypothèses et options abandonnées

**Option A — conditions en dur**
- *Ce qu'elle proposait* : la règle écrite là où elle s'applique.
- *Pourquoi elle était séduisante* : c'est la solution honnête pour **une** règle. Le calcul se lit
  du haut vers le bas sans sauter de fichier, et l'on évite précisément l'abstraction spéculative que
  le projet s'interdit. Avec une seule règle, elle est objectivement plus simple.
- *Ce qui l'a disqualifiée* : ajouter la deuxième règle demanderait de rouvrir le moteur et de
  reprendre ses tests — ce que la décision M2 refuse explicitement. Et il faudrait de toute façon
  construire à côté la liste des règles actives pour la persister.
- *Ce qui nous y ferait revenir* : si, à la fin du projet, `labour` est toujours la seule règle et
  que personne n'en a demandé d'autre, le registre aura été une erreur : on aplatit.

**Option C — DSL en base**
- *Ce qu'elle proposait* : des règles comme données, modifiables sans redéploiement.
- *Pourquoi elle était séduisante* : c'est la forme extrême de « facile d'en rajouter » — le métier
  écrirait ses propres règles, et l'outil deviendrait paramétrable sans nous. Pour un remplaçant
  d'Excel, où l'utilisateur avait justement le pouvoir d'écrire ses formules, l'argument porte.
- *Ce qui l'a disqualifiée* : un langage d'expressions est un projet en soi — analyse, évaluation
  sûre, messages d'erreur, tests, documentation — pour zéro besoin exprimé et une seule règle
  existante. Et des formules stockées en base sont bien plus difficiles à rendre reproductibles.
- *Ce qui nous y ferait revenir* : si un utilisateur non développeur devait créer des règles sans
  passer par l'équipe.

**Hypothèses de travail**
- Deux méthodes (`applies_to`, `apply`) suffiront à la deuxième règle. *Risque* : si la deuxième
  règle a besoin du contexte global (autres pièces, total partiel), l'interface devra changer — et
  le registre n'aura rien fait gagner.
- L'ordre d'application est **déterministe** (ordre d'enregistrement explicite, pas l'ordre
  d'import). *Risque* : un ordre non déterministe casserait la reproductibilité sans bruit, dès la
  deuxième règle.

## Conséquences

**Positives**
- Ajouter une règle : un fichier, un test, une ligne d'enregistrement ; le moteur ne bouge pas.
- Les règles actives sont persistées avec le calcul : la reproductibilité est servie par le même
  mécanisme.
- L'explication peut attribuer un montant à une règle nommée.

**Négatives**
- Une indirection existe aujourd'hui pour une seule règle : le lecteur doit ouvrir deux fichiers là
  où un aurait suffi.
- L'ordre d'application devient une chose à documenter et à protéger.

**Dette acceptée**
- Pas de règles paramétrables par l'utilisateur au-delà de l'activation ; pas de règles par pièce ou
  par système — une règle est active pour tout le calcul.

## Comment on saura qu'on s'est trompé

Au moment d'ajouter la deuxième règle, l'interface ne suffit pas et doit être modifiée : le registre
n'aura servi à rien. Ou bien, à la fin du projet, `labour` est restée seule.
