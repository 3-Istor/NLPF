# ADR-0011 — Le calcul se fait en décimal exact ; l'arrondi est un acte d'affichage

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor — décision validée le 2026-09-22

## Contexte et problème

L'invariant central du projet dit que **la somme des contributions égale le total, au centime**. Or un
total se construit ici en multipliant trois facteurs (prix de référence × multiplicateur fournisseur
× coefficient d'usine, ADR-0010), puis en agrégeant plusieurs centaines de lignes le long d'un
graphe. Chaque endroit où l'on arrondit est un endroit où la somme peut cesser de tomber juste.

Il faut donc décider **où vit la précision** : dans le moteur, dans la base, dans le transport, à
l'écran — et avec quelle règle d'arrondi.

## Critères de décision

1. **L'invariant de conservation doit être vrai exactement**, pas à un écart d'arrondi près.
   *Décisif.*
2. Reproductibilité : deux calculs identiques donnent le même chiffre, quel que soit l'ordre
   d'agrégation.
3. Lisibilité pour l'utilisateur : ce qu'il voit doit être un montant, pas une suite de décimales.
4. Simplicité : un seul endroit dans le code décide de l'arrondi.

## Options envisagées

### Option A — Décimal exact partout, arrondi au dernier moment
Calcul et stockage en décimal à 6 décimales (`Decimal` côté Python, `NUMERIC(18,6)` côté Postgres).
Aucun arrondi dans le moteur, aucun dans la base, aucun dans le transport. L'arrondi à 2 décimales,
en `ROUND_HALF_UP`, se fait **uniquement à l'affichage**.
*Apporte* : l'invariant est vrai au sens strict ; l'ordre d'agrégation n'a aucune influence.
*Coûte* : les montants transportés par l'API ne sont pas ceux affichés, ce qu'il faut expliquer.

### Option B — Arrondi à chaque ligne, stockage en `NUMERIC(12,2)`
Chaque contribution est arrondie au centime dès son calcul.
*Apporte* : ce qui est stocké est exactement ce qui est affiché.
*Coûte* : la somme de 350 lignes arrondies ne retombe pas sur le total arrondi.

### Option C — Flottants (`float` / `double precision`)
Le type numérique par défaut.
*Apporte* : le type natif, rapide, aucune conversion.
*Coûte* : `0.1 + 0.2 ≠ 0.3`.

## Décision

**Option A.**

Raison décisive : l'arrondi par ligne (option B) obligerait à afficher une ligne « écart d'arrondi »
pour que les comptes tombent — c'est-à-dire à avouer que la décomposition ne reconstitue pas le
total. Dans un outil dont la valeur est l'explicabilité, c'est rédhibitoire.

Règles retenues :
- **Interne et stockage** : décimal exact, échelle 6. Les coefficients (multiplicateur, coefficient
  d'usine) sont eux aussi des décimaux à 6 décimales.
- **Transport** : l'API renvoie les montants comme **chaînes décimales** à 6 décimales, jamais comme
  nombres flottants JSON.
- **Affichage** : arrondi à 2 décimales, `ROUND_HALF_UP`, dans **un seul** utilitaire de formatage
  côté front.
- **Frontière à ne pas franchir** : arrondir pour afficher est du **formatage** ; additionner,
  multiplier ou convertir des montants côté navigateur reste interdit (ADR-0009).

## Hypothèses et options abandonnées

**Option B — arrondi à la ligne**
- *Ce qu'elle proposait* : arrondir chaque contribution au centime dès son calcul.
- *Pourquoi elle était séduisante* : ce qui est en base est exactement ce qui est à l'écran, ce qui
  supprime toute question de cohérence entre les deux. Elle facilite aussi la comparaison ligne à
  ligne avec le classeur Excel existant, qui arrondit de la même façon — argument réel au moment de
  vérifier que le nouvel outil dit la même chose que l'ancien.
- *Ce qui l'a disqualifiée* : la somme des contributions arrondies dérive du total arrondi de
  quelques centimes sur une nomenclature de cette taille. L'invariant deviendrait « égal à quelques
  centimes près », ce qui n'est plus un invariant.
- *Ce qui nous y ferait revenir* : si un référentiel externe (facturation, comptabilité) imposait des
  montants arrondis à la ligne. L'arrondi serait alors une règle métier, avec sa ligne d'écart
  assumée.

**Option C — flottants**
- *Ce qu'elle proposait* : `float` partout.
- *Pourquoi elle était séduisante* : c'est le type par défaut de JSON, de NumPy et de la plupart des
  bibliothèques ; aucune conversion, aucune question à se poser, et l'erreur est de l'ordre de
  10⁻¹⁵ — donc « invisible ».
- *Ce qui l'a disqualifiée* : elle n'est pas invisible ici. La mémoïsation change l'ordre dans lequel
  les contributions s'agrègent ; avec des flottants, deux exécutions du même calcul peuvent différer
  au dernier chiffre, et la reproductibilité au centime cesse d'être démontrable.
- *Ce qui nous y ferait revenir* : jamais pour de la monnaie. Éventuellement pour des grandeurs
  physiques indicatives (masses), et encore.

**Hypothèses de travail**
- **Six décimales suffisent** en interne : le produit de trois facteurs à 6 décimales reste
  représentable sans perte significative devant un centime. *Risque* : un prix unitaire très faible
  (une vis à 0,004 €) multiplié par une grande quantité cumulée reste juste, mais son affichage à
  2 décimales sera « 0,00 € » ligne à ligne — l'écran doit afficher la **contribution**, pas
  seulement le prix unitaire.
- **`ROUND_HALF_UP`** plutôt que l'arrondi bancaire : convention usuelle en devis industriel. *Risque*
  : un référentiel comptable pourrait exiger `ROUND_HALF_EVEN`. Le changement porte alors sur un seul
  utilitaire.
- Les **pourcentages** de la décomposition par système sont calculés côté serveur, à une décimale.
  *Risque* : arrondis, ils peuvent totaliser 99,9 % ou 100,1 %. Le critère d'acceptation porte sur les
  **montants**, pas sur les pourcentages ; c'est assumé et doit être dit à l'écran si la somme
  affichée dérange.

## Conséquences

**Positives**
- L'invariant de conservation est vrai au sens strict, et testable par égalité exacte.
- L'ordre d'agrégation n'a aucun effet : la mémoïsation ne peut pas changer un résultat.
- Un seul endroit dans tout le code décide de l'arrondi.

**Négatives**
- Les montants de l'API (`"39.742800"`) ne sont pas ceux de l'écran (`39,74 €`) : il faut l'expliquer,
  et une capture d'API dans un rapport surprendra.
- Les montants circulent en chaînes de caractères, pas en nombres JSON : tout client doit le savoir.
- Les pourcentages affichés peuvent ne pas totaliser exactement 100 %.

**Dette acceptée**
- Pas de répartition du reste (méthode du plus fort reste) sur les pourcentages ni sur des montants
  arrondis destinés à être resommés à l'écran. Si un besoin d'affichage resommable apparaît, ce sera
  une nouvelle décision.

## Comment on saura qu'on s'est trompé

Un test de propriété trouve un écart, même d'un centime, entre le total et la somme des
contributions ; ou un utilisateur additionne les montants affichés et retombe à côté du total, ce qui
signifierait que l'écran donne à croire qu'ils sont resommables.
