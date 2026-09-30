# ADR-0012 — Comparer deux scénarios sur un même snapshot ; recommander le sourcing pièce par pièce

- **Date** : 2026-09-30
- **Statut** : proposé — à valider par l'équipe (revue de la PR `feature/scenarios-aide-decision`)
- **Décideurs** : équipe 3istor

## Contexte et problème

La décision D1 du périmètre disait : l'outil **montre** l'effet d'un changement, il ne cherche pas la
meilleure combinaison. La tranche T3 (« l'outil aide à décider ») demande deux choses que D1 ne
couvrait pas :

- répondre à « combien me coûte la variante B par rapport à A, et où ? » (questions Q3 et Q5 du
  cadrage, et le report §3.5 du périmètre) ;
- proposer, sous contraintes d'origine et de délai, un sourcing moins cher que l'actuel.

Deux dangers propres au projet. Une comparaison qui mélange un changement de prix externe et un
changement de paramètre attribue au scénario ce qui vient du marché. Et une « optimisation » sur un
DAG de ~350 nœuds achetés peut manger la soutenance sans rien démontrer sur le graphe (périmètre
§3.1).

## Critères de décision

1. **Un écart affiché doit être attribuable au seul scénario.** *Décisif.*
2. Un prix manquant n'est jamais un zéro, même dans un delta.
3. La recommandation doit être explicable ligne à ligne : pièce, option actuelle, option proposée,
   quantité, économie.
4. Le scénario d'origine n'est jamais modifié par une recommandation.
5. Le moteur reste une fonction pure appelée pour vérifier exactement le scénario proposé.

## Options envisagées

### Option A — Comparaison sur snapshot commun, recommandation indépendante par pièce
A et B sont recalculés avec **le même snapshot**. Le delta vaut B − A, décomposé par
`own_contribution`. La recommandation examine chaque pièce achetée séparément et retient l'option
fournisseur × usine la moins chère parmi celles autorisées.
*Apporte* : un delta attribuable ; une recommandation qu'on explique en une ligne par pièce.
*Coûte* : aucune contrainte couplée (« au plus deux fournisseurs », « budget CO₂ global »).

### Option B — Optimisation combinatoire globale
Un solveur choisit la combinaison qui minimise le total sous contraintes globales.
*Apporte* : des contraintes couplées.
*Coûte* : une dépendance, un modèle à maintenir, une réponse difficile à expliquer ; exactement ce
que §3.1 du périmètre reporte.

### Option C — Comparer les derniers calculs enregistrés, tels quels
*Apporte* : aucun recalcul.
*Coûte* : A et B peuvent avoir été calculés sur deux snapshots différents ; le delta mélange alors
marché et scénario.

## Décision

**Option A.**

Raison décisive : sans contrainte couplée, le problème est **séparable** — le coût total est une
somme de contributions qui ne dépendent que du sourcing de leur propre pièce. Le minimum pièce par
pièce est donc le minimum global. Un solveur n'apporte rien tant qu'aucune contrainte ne relie deux
pièces.

Règles retenues :

- **Comparaison** : les deux scénarios sont recalculés sur un snapshot commun (le plus récent, ou
  celui demandé). Même version de BOM et même devise d'affichage exigées. Un calcul `INCOMPLETE`
  d'un côté ou de l'autre est refusé. `co2_delta_kg` reste `null` tant que le CO₂ n'est pas calculé,
  jamais `0`.
- **Recommandation** :
  - le calcul de base doit être complet ;
  - une pièce avec **prix forcé** est laissée telle quelle : le prix forcé est une décision humaine
    justifiée ;
  - les occurrences couvertes par un paramètre de **portée chemin** sont exclues de la quantité
    affectée : la surcharge la plus spécifique gagne (ADR-0002) ;
  - si l'option actuelle **viole une contrainte**, l'option autorisée la moins chère est proposée
    même si elle coûte plus cher ; l'économie est alors négative et la ligne est marquée
    `required_by_constraint` ;
  - si l'option actuelle viole une contrainte et **qu'aucune option autorisée n'existe**, la pièce est
    listée dans `unresolved` avec sa raison. Elle n'est jamais ignorée en silence : la variante créée
    garderait sinon une provenance interdite sans le dire ;
  - la recommandation crée toujours un **nouveau** scénario ; l'utilisateur choisit les lignes
    acceptées.

## Hypothèses et options abandonnées

**Option B — solveur global**
- *Ce qu'elle proposait* : minimiser le total sous contraintes globales.
- *Pourquoi elle était séduisante* : c'est ce qu'un acheteur imagine derrière « optimiser », et elle
  ouvre la porte aux contraintes CO₂ globales.
- *Ce qui l'a disqualifiée* : sans contrainte couplée, elle donne la même réponse que l'option A, en
  plus cher et moins explicable.
- *Ce qui nous y ferait revenir* : une contrainte qui relie plusieurs pièces est exprimée
  explicitement (plafond de CO₂ global, nombre maximal de fournisseurs, volume minimal par
  fournisseur). C'est le déclencheur §3.1 du périmètre.

**Option C — comparer les calculs existants**
- *Ce qu'elle proposait* : lire les deux derniers calculs sans recalculer.
- *Pourquoi elle était séduisante* : aucun coût de calcul, et elle répond littéralement à « qu'est-ce
  qui a changé depuis lundi ? ».
- *Ce qui l'a disqualifiée* : un écart de snapshot passerait pour un effet de scénario.
- *Ce qui nous y ferait revenir* : si l'on veut expliquer un écart **dans le temps** ; il faudrait
  alors le décomposer en effet prix et effet scénario, ce qui est une autre fonctionnalité.

**Hypothèses de travail**
- Le délai fournisseur et l'origine sont portés par l'**usine**, pas par l'offre. *Risque* : un délai
  qui dépend de la pièce demanderait un champ sur l'offre.
- La devise d'achat (`purchase_currency`) n'intervient pas : aucune conversion n'existe encore.
  *Risque* : une recommandation qui comparerait des prix en devises différentes serait fausse ; à
  reprendre avec la tranche devises.

## Conséquences

**Positives**
- Le delta B − A s'explique ligne à ligne, et la somme des écarts vaut le delta total.
- La recommandation reste une suite d'appels au moteur pur : aucune logique de coût dupliquée.
- La décision D1 évolue sans rouvrir le report §3.1.

**Négatives**
- Chaque comparaison et chaque recommandation enregistre de nouveaux calculs : la table `calculation`
  grossit plus vite.
- Les contraintes couplées restent inexprimables.

**Dette acceptée**
- Pas de compromis coût/CO₂ dans la recommandation tant que le CO₂ n'est pas calculé ; la règle
  (plafond de CO₂, plafond de coût, ou front de Pareto présenté sans choisir) sera une nouvelle
  décision.

## Comment on saura qu'on s'est trompé

Un utilisateur applique une recommandation et découvre une contrainte que l'outil n'a pas pu
exprimer (deux pièces qui doivent venir du même fournisseur) ; ou une comparaison affiche un écart
qui disparaît en recalculant les deux scénarios sur le snapshot suivant, ce qui voudrait dire que le
snapshot commun n'a pas été respecté.
