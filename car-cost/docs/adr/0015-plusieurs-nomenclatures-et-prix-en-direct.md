# ADR-0015 — Plusieurs nomenclatures, des prix simulés, en direct ou figés

- **Date** : 2026-10-02
- **Statut** : proposé
- **Décideurs** : équipe 3istor — à accepter en revue de la PR `feat/multi-bom-prix-fournisseurs`

## Contexte et problème

La PR #6 a apporté trois nomenclatures Aston Martin Valhalla (hybride, thermique, électrique) et un
simulateur de prix sur une année de marché, mais à côté du produit : une route `/api/prices` qui
renvoyait le JSON source avec des prix recalculés, sans lien avec la nomenclature en base, le
calcul, les snapshots ni l'écran.

On veut désormais :

1. choisir à l'écran la nomenclature à étudier, parmi le Multipla et les trois Valhalla ;
2. compter ou non le SAV (pièces de rechange livrées avec le véhicule) que portent les Valhalla ;
3. des prix qui **varient**, lus soit **en direct** (le prix de l'API à l'instant), soit **figés**
   dans un snapshot comme aujourd'hui ;
4. voir, pièce par pièce, la variation de son prix sur l'année simulée.

Le point 3 touche l'ADR-0003 : un calcul doit être rejouable au centime. Un prix « en direct »
ne l'est pas par nature.

## Critères de décision

1. **Ne pas affaiblir l'ADR-0003** : tout total enregistré reste rejouable. *Décisif.*
2. Une seule façon de calculer : pas de moteur bis pour la Valhalla ni pour le direct.
3. Le simulateur reste une source externe que le produit sait voir tomber.
4. Ne jamais attribuer à un véhicule les prix d'un autre.

## Décision

**Les Valhalla deviennent des nomenclatures du produit.** `tools/valhalla_import` convertit les
fichiers source au format du Multipla (véhicule → catégorie → [sous-catégorie] → lignes achetées)
et génère, de façon déterministe, ce qu'ils ne disent pas (masse, carbone, main-d'œuvre, usines,
fournisseurs alternatifs). Le chargeur et le moteur ne font aucune différence.

**Le simulateur vit dans la mock API**, pas dans le backend. Le contrat `GET /prices` ne change
pas ; les pannes non plus. `GET /history` y est ajouté pour le graphe.

**Un snapshot de prix porte sa nomenclature.** Le calcul prend le dernier snapshot **de la
nomenclature du scénario** ; à défaut, un snapshot pris avant cette décision (sans nomenclature).
Chaque nomenclature reçoit son premier snapshot au démarrage.

**Deux modes de prix, un seul calcul.**

- *Snapshot* : inchangé. On peut désormais prendre un snapshot depuis l'écran
  (`POST /api/v1/price-snapshots`), avec les mêmes contrôles et le même repli qu'en ligne de
  commande.
- *Direct* : `POST /api/v1/calculations/live` interroge l'API, construit un snapshot de prix
  **transitoire** et appelle le même `run_calculation`. Le résultat est marqué `price_mode: LIVE`
  et **n'est jamais enregistré** : ni calcul en base, ni snapshot de prix, ni snapshot de calcul.
  Il est gardé en mémoire, quelques dizaines au plus, le temps que l'arbre lise ses lignes. Pour
  garder un chiffre, on fige les prix (snapshot), puis on calcule.

**Le SAV est un réglage du scénario**, porté par l'arête (`after_sales_quantity`) et ajouté aux
quantités avant le moteur. Il entre dans l'empreinte des entrées et dans la copie d'un calcul figé.

## Options écartées

- **Garder la route `/api/prices` de la PR #6** : deuxième modèle de nomenclature, deuxième calcul,
  aucun lien avec les scénarios. Deux vérités qui finissent par diverger.
- **Persister les calculs en direct** : un calcul toutes les cinq secondes par écran ouvert remplit
  la table de totaux que personne n'a demandé à garder, chacun citant un snapshot inexistant.
- **Un snapshot par appel en direct** : rejouable, mais des milliers de snapshots par heure, et la
  liste des snapshots devient illisible. Figer reste un geste explicite.

## Conséquences

- Un total affiché en mode direct n'a pas d'identifiant durable : on ne le compare pas, on ne le
  fige pas. L'écran le dit et propose de figer les prix.
- Le serveur garde en mémoire les derniers calculs en direct ; un redémarrage les oublie, ce qui
  est voulu.
- Les données Valhalla générées sont synthétiques, comme le reste ; leur provenance est écrite
  dans les métadonnées des fichiers.
