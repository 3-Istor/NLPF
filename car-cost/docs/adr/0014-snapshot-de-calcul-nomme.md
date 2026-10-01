# ADR-0014 — Un snapshot de calcul nommé fige un calcul, autonome et immuable

- **Date** : 2026-10-01
- **Statut** : proposé
- **Décideurs** : équipe 3istor — à valider en revue de la PR qui l'introduit

## Contexte et problème

Un calcul est enregistré avec ses versions (BOM, snapshot de prix, règles) et sa devise, mais le
scénario qui l'a produit continue de bouger : on en modifie les paramètres, on le recalcule, on le
supprime. Le résultat « retenu » d'une étude n'a donc pas de support stable. On veut pouvoir figer
un résultat **et** les hypothèses qui l'ont produit au même instant, lui donner un nom, le rouvrir
et le comparer plus tard à un autre. On veut aussi, au lot 3, l'exporter et l'importer : le modèle
doit dès maintenant se suffire à lui-même.

**Collision de vocabulaire.** Le *snapshot de prix* (`PriceSnapshot`, ADR-0003) est une photographie
datée des prix ; il garde ce sens. Ce que l'on introduit ici est un *snapshot de calcul*
(`CalculationSnapshot`) : un calcul nommé, figé, avec ses hypothèses. Les deux mots ne se
substituent jamais l'un à l'autre.

## Critères de décision

1. **Reproductibilité et autonomie** : le snapshot se relit et s'exporte sans le scénario vivant. *Décisif.*
2. Ne pas casser le snapshot de prix (ADR-0003, immuable, partagé par tous les calculs).
3. Ne pas casser la comparaison de scénarios existante (ADR-0012).
4. Un nom qui a un sens pour l'utilisateur, sans ambiguïté.

## Options envisagées

### Option A — Un nom sur le snapshot de prix
*Apporte* : rien de nouveau à stocker.
*Coûte* : un snapshot de prix est partagé par tous les calculs faits entre deux prises de prix ;
le nommer n'identifie aucun calcul, et ne fige ni les paramètres ni le résultat.

### Option B — Un nom sur le calcul
*Apporte* : une table de moins.
*Coûte* : un calcul référence le scénario vivant pour ses paramètres, qui changent ; le calcul
n'est pas autonome, donc pas exportable. Et mêler « nommé » et « courant » dans la même table
obscurcit la règle « le dernier calcul d'un scénario ».

### Option C — Une nouvelle entité, `CalculationSnapshot`
Une copie figée des hypothèses, plus des références vers le calcul, le snapshot de prix et la
version de BOM validée. Immuable, sauf le nom.
*Apporte* : l'autonomie, une identité propre, aucun effet sur les entités existantes.
*Coûte* : une table et un cycle de vie de plus.

## Décision

**Option C.** Raison décisive : seule une copie rend le snapshot autonome, donc exportable (lot 3).

Règles retenues :
- **Figer sous un nom, c'est lancer un calcul maintenant** : réglages et snapshot de prix courants,
  figés dans la même opération. Il n'y a pas de refus « calcul obsolète » : on ne fige jamais un
  vieux calcul. Un calcul `INCOMPLETE` peut être figé et **garde son statut**.
- **Copie** des paramètres exactement appliqués (portée, chemin, fournisseur, usine, devise
  d'achat, prix forcé et justification, main-d'œuvre), du taux horaire, de la devise d'affichage,
  des règles actives et du nom du scénario. **Références** vers le calcul, le snapshot de prix et
  la version de BOM **validée** (ADR-0013).
- **Nom obligatoire**, rogné ; l'écran en propose un par défaut, modifiable. Il n'y a pas de valeur
  de repli : aucun snapshot n'existe sans nom. Unique **par version de BOM**, sans casse ni accents :
  `name_key = fold(name)`, le même pliage que la recherche, calculé en Python et protégé par un
  index unique en base.
- **Renommable**, le nom seul ; chaque renommage est tracé en ajout seul. Pas d'interface de
  renommage au lot 1.
- **Immuable** pour tout le reste. **Suppression d'un snapshot refusée.** Supprimer un scénario qui
  porte au moins un snapshot est refusé : `409 SCENARIO_HAS_SNAPSHOTS`.
- **Comparaison** : celle des scénarios (ADR-0012) reste intacte. On **ajoute** la comparaison de
  deux snapshots de calcul, sans recalcul et sans enregistrement, sur le **même snapshot de prix**.
  Deux snapshots sur des snapshots de prix différents sont refusés (`INCOMPARABLE_SCENARIOS`).
  Raison : les prix se prennent à la main, donc deux gels faits entre deux prises de prix partagent
  le même snapshot de prix ; et la décomposition de l'écart (prix, quantité, conception) est une
  règle métier absente, objectif central de la vue direction (lot 2.3), à lever alors.

## Hypothèses et options abandonnées

**Option A — nom sur le snapshot de prix** : écartée, il ne désigne pas un calcul.
**Option B — nom sur le calcul** : écartée, le calcul n'est pas autonome.

**Hypothèses de travail**
- Un snapshot de prix ne se prend qu'à la main ou au premier démarrage, jamais au calcul : le refus
  de comparer à travers deux snapshots de prix reste rarement rencontré. *Risque* : si la prise
  devient planifiée, il le sera souvent, et la décomposition de l'écart devient urgente.

## Conséquences

- Une table de snapshots, sa trace de renommages et un port dans `application/ports.py` (D8, emplacement
  des ports en attente de l'équipe). L'entité vit dans `domain/calculation_snapshot.py`.
- Limites connues : un snapshot importé ne se modifie pas ; le modifier crée un scénario dérivé
  dont le gel produit un nouveau snapshot (`derived_from`, « partir de ce snapshot »), au lot 3,
  comme l'export et l'import. Les marques ●/○ d'un snapshot ouvert viennent du scénario vivant.
- Le glossaire (§6) distingue « snapshot de prix » et « snapshot de calcul ».
