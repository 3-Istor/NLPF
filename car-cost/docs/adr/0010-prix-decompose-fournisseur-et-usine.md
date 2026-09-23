# ADR-0010 — Le prix d'achat se décompose en prix de référence × multiplicateur fournisseur × coefficient d'usine

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor — décision M1, validée le 2026-09-22 : « la provenance est un levier
  indépendant — même fournisseur, usine différente — et porte son propre effet sur le prix et le CO₂ »

## Contexte et problème

L'écran demande, sur une pièce achetée, **deux** champs distincts : le fournisseur et la provenance.
Or si la provenance était simplement l'adresse du fournisseur, choisir l'un fixerait l'autre et le
second champ ne serait qu'un affichage.

La décision M1 tranche : la provenance est un **levier indépendant**. Un même fournisseur peut
livrer depuis plusieurs sites, et le site choisi change le prix et le CO₂ de transport. Comme l'API
de prix est écrite par nous, nous décidons aussi de la forme de la donnée — donc cette décision
engage à la fois le modèle de coût, le jeu de données et l'écran.

## Critères de décision

1. **Les deux leviers doivent être réglables séparément et lisibles séparément** dans l'explication.
   *Décisif — c'est la demande.*
2. Ne présenter aucun chiffre inventé comme une donnée réelle.
3. Plausibilité industrielle de la structure.
4. Coût pour le générateur, le moteur et l'interface.

## Options envisagées

### Option A — Décomposition multiplicative
```
prix unitaire = prix de référence (snapshot, devise)
              × multiplicateur fournisseur      (sa marge, sa qualité, son service)
              × coefficient d'usine             (le coût du site retenu)
CO₂ transport = porté par l'usine
```
Un fournisseur déclare ses sites ; le choix d'usine se fait **parmi les sites du fournisseur retenu**.
*Apporte* : chaque facteur est isolable et affichable ; changer un levier ne touche pas l'autre.
*Coûte* : un facteur de plus dans chaque prix, chaque test et chaque explication.

### Option B — Grille de prix par couple (fournisseur, usine)
Chaque couple porte son propre prix négocié.
*Apporte* : représente n'importe quelle grille tarifaire réelle, y compris non multiplicative.
*Coûte* : le prix cesse d'être décomposable.

### Option C — Provenance dérivée du fournisseur
Le fournisseur porte son origine ; la provenance est affichée en lecture seule.
*Apporte* : un levier de moins, aucune donnée supplémentaire à produire.
*Coûte* : « même fournisseur, usine différente » devient inexprimable.

## Décision

**Option A**, avec la contrainte que **les usines disponibles dépendent du fournisseur choisi**.

Raison décisive : la décomposition multiplicative est la seule forme où l'explication peut répondre à
la question posée — « que me coûte le choix de cette usine ? » — indépendamment du fournisseur. Une
ligne d'explication se lit alors littéralement :

> `40,00 € (référence) × 1,08 (fournisseur Ricambi) × 0,92 (usine de Bursa, TR) = 39,74 €`
> `+ 0,31 kg CO₂e de transport (Bursa → Turin)`

Conséquences de forme, à répercuter dans le jeu de données : `suppliers.json` gagne un niveau —
fournisseur → sites — chaque site portant origine, coefficient de prix, délai et CO₂ de transport.
Le scénario porte donc **deux** paramètres sur une pièce achetée : `supplier_id` et `plant_id`.

## Hypothèses et options abandonnées

**Option B — grille par couple**
- *Ce qu'elle proposait* : un prix propre à chaque couple (fournisseur, usine).
- *Pourquoi elle était séduisante* : c'est la vérité des achats. Les remises, les accords-cadres et
  les prix négociés ne se déduisent d'aucun coefficient, et une grille les représente tous sans
  contorsion. Elle serait aussi plus simple à alimenter depuis un vrai système d'achat.
- *Ce qui l'a disqualifiée* : elle rend le prix **non décomposable**. On ne pourrait plus dire ce que
  coûte le choix de l'usine séparément de celui du fournisseur, alors que c'est exactement la
  question que M1 demande de rendre visible.
- *Ce qui nous y ferait revenir* : le premier prix négocié réel à intégrer, qui ne se déduirait
  d'aucun coefficient. On garderait alors la décomposition pour l'explication, avec un prix de couple
  qui la remplace quand il existe.

**Option C — provenance dérivée**
- *Ce qu'elle proposait* : la provenance comme attribut du fournisseur, non réglable.
- *Pourquoi elle était séduisante* : un levier de moins à comprendre, à tester et à afficher ; aucun
  coefficient d'usine à inventer, donc aucun chiffre synthétique supplémentaire à assumer ; et
  l'interface se simplifie — un seul choix au lieu de deux imbriqués.
- *Ce qui l'a disqualifiée* : décision explicite M1. Elle rendrait par ailleurs l'arbitrage
  coût/CO₂ (question métier Q5) beaucoup plus grossier, puisqu'on ne pourrait le jouer qu'en
  changeant de fournisseur.
- *Ce qui nous y ferait revenir* : si l'usage montrait que personne ne change jamais d'usine sans
  changer de fournisseur — mesurable sur les scénarios enregistrés.

**Hypothèses de travail**
- Les coefficients d'usine et les CO₂ de transport sont **synthétiques**, construits pour être
  cohérents entre eux : une usine lointaine et peu chère porte un coefficient inférieur à 1 **et** un
  CO₂ de transport plus élevé, de façon que l'arbitrage existe vraiment. *Risque* : ces chiffres ne
  représentent aucune usine réelle ; ils sont déclarés comme tels dans les métadonnées du jeu de
  données et dans l'interface.
- Le multiplicateur fournisseur et le coefficient d'usine sont **indépendants** (leur produit a un
  sens). *Risque* : dans la réalité ils ne le sont pas toujours ; un fournisseur bon marché n'a pas
  les mêmes sites qu'un fournisseur premium.
- Ces deux facteurs ne sont **pas** des règles activables (ADR-0006) : les désactiver produirait un
  prix qui ne correspond à aucun achat possible.

## Conséquences

**Positives**
- Les deux leviers demandés existent et sont lisibles séparément dans l'explication.
- L'arbitrage coût/CO₂ devient jouable sans changer de fournisseur, ce qui sert directement Q5.
- Le prix reste entièrement traçable : trois facteurs, trois origines de donnée.

**Négatives**
- Un facteur de plus partout : dans le générateur, dans le moteur, dans chaque test de prix, dans
  chaque ligne d'explication.
- `suppliers.json` gagne un niveau de profondeur, et le jeu de données porte un jeu de chiffres
  synthétiques de plus à justifier.
- L'interface doit **invalider le choix d'usine** quand on change de fournisseur — un état de plus à
  gérer, et une source d'erreur si on l'oublie.

**Dette acceptée**
- Pas de prix négocié par couple, pas de remise sur quantité, pas de seuil de commande minimum.

## Comment on saura qu'on s'est trompé

Aucun scénario enregistré ne contient de changement d'usine sans changement de fournisseur — le
levier n'aura servi à rien ; ou un besoin de prix négocié apparaît, qui ne rentre dans aucun
coefficient.
