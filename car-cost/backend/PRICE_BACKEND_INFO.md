# Dynamic Pricing Backend

Référence d'utilisation du backend de la branche `prix`. Les données et indices
sont **synthétiques** : ils ne représentent pas des prix constructeur.

## 1. Rôle du backend prix

Le backend gère les prix dynamiques de la BOM Aston Martin Valhalla, soit environ
635 lignes de composants. Chaque composant possède notamment un `id`, un `nom`,
une quantité, un fournisseur, un prix de base et une garantie.

Le moteur calcule le prix courant à partir d'indices économiques simulés.
Les autres équipes n'ont pas besoin de connaître sa logique interne : elles
appellent uniquement les endpoints de la section 7 et utilisent les coûts retournés.

```text
request API
→ temps simulé
→ indices économiques courants
→ drivers du composant
→ prix unitaire dynamique
→ quantité
→ coût retourné
```

## 2. Fonctionnement de la simulation

**1 année simulée = 40 minutes réelles.** La simulation boucle après 365 jours.
Le temps simulé vient du temps réel ; aucune boucle de recalcul permanente ne
fonctionne en arrière-plan. Le calcul se fait à chaque requête : deux appels
espacés de quelques secondes peuvent donc retourner des prix différents.

```text
SECONDS_YEAR = 365 * 24 * 60 * 60
SIM_DURATION = 40 * 60
SPEED = SECONDS_YEAR / SIM_DURATION

temps_simule = (time.time() - start_time) * SPEED
position_dans_annee = temps_simule % SECONDS_YEAR
```

La date simulée commence au 1er janvier 2026 UTC. Un redémarrage remet la
simulation à zéro. Chaque requête utilise un même instant pour tous ses calculs ;
deux requêtes distinctes peuvent correspondre à des instants différents.

## 3. Indices économiques utilisés

- `cuivre`
- `aluminium`
- `acier`
- `lithium`
- `nickel`
- `energie`
- `transport`
- `semi_conducteurs`
- `GBP_EUR`

Les historiques locaux contiennent 365 valeurs par indice. Ils sont chargés en
RAM au démarrage, comme la BOM. Aucun accès Internet n'est nécessaire pendant
l'exécution ; les GET prix ne lisent ni disque ni base de données.

Les valeurs sont interpolées linéairement entre deux jours pour faire évoluer
les prix continuellement : `indice_J + progression * (indice_J1 - indice_J)`.
La progression vient directement de l'horloge simulée. Le dernier jour rejoint
le premier pour conserver la continuité au bouclage.

## 4. Calcul du prix dynamique

```text
variation_indice = indice_actuel / indice_initial - 1
facteur_prix = 1 + somme(coefficient_driver * variation_indice)
prix_unitaire_actuel_eur = prix_unitaire_base_eur * facteur_prix
cout_par_voiture = prix_unitaire_actuel_eur * quantite
```

Le prix de base du JSON n'est jamais modifié. Les coefficients dépendent du type
de composant et sont normalisés : leur somme vaut 1. L'énergie sert également
d'approximation pour les matières plastiques et le caoutchouc.

`GBP_EUR` intervient uniquement lorsque la **devise du fournisseur est GBP**.
Pour un fournisseur en EUR, son poids est nul et les autres coefficients sont
renormalisés proportionnellement : aucun effet GBP/EUR n'est appliqué.

## 5. Garantie et stock SAV

La garantie **ne modifie pas le prix unitaire** : elle augmente uniquement la
quantité à acheter. Le taux SAV par défaut est `SAV_RATE = 0.03`, soit 3 %.

```text
quantite_production = quantite_par_voiture * nombre_voitures

si garantie == true :
    quantite_achat = ceil(quantite_production * 1.03)
sinon :
    quantite_achat = quantite_production

cout_total_ligne = quantite_achat * prix_unitaire_actuel_eur
```

Le plafond est appliqué par composant sous garantie, après multiplication par
le nombre de voitures. Il constitue une réserve SAV sans augmenter artificiellement
le prix d'une pièce. Le coût du stock SAV correspond uniquement aux unités
supplémentaires ; le coût BOM d'une voiture exclut cette réserve.

## 6. Démarrage local

Depuis la racine du dépôt, dans un environnement où le backend et ses dépendances
existantes sont installés :

```bash
export CARCOST_PRICE_BOM=/chemin/vers/aston_martin_valhalla_bom_simple.json
python -m uvicorn carcost.infrastructure.api.main:app --port 8000 --workers 1
```

Le JSON reste à cet emplacement, sans copie. Utiliser `export` pour transmettre
la variable à Python. Garder un seul worker pour partager la même horloge de
simulation. Redémarrer après un changement de configuration ou de fichier.

Base locale : `http://localhost:8000`. Documentation interactive :
`http://localhost:8000/docs`.

## 7. API à appeler

Tous les endpoints ci-dessous utilisent **GET**, avec un seul préfixe `/api`.
Les montants, indices, pourcentages et quantités sont des **chaînes décimales**,
par exemple `"10.25"`, sans arrondi d'affichage. `vehicles` est un entier JSON ;
`date_simulee` est une date et heure ISO 8601 en UTC.

| Endpoint | Utilisation et réponse |
|---|---|
| `/api/prices` | Tableau JSON de tous les composants, avec les champs décrits ci-dessous. |
| `/api/prices/{component_id}` | Même information pour un seul composant, sous forme d'objet JSON. Utiliser son ID inchangé, par exemple `BOM-0003`. |
| `/api/vehicle-cost` | Coût BOM d'une voiture, hors réserve SAV : `date_simulee`, `cout_bom_eur`, `variation_pct_depuis_debut`. |
| `/api/production-cost?vehicles=100` | Coût de fabrication et réserve SAV pour N voitures : `vehicles`, `cout_production_eur`, `cout_stock_sav_eur`, `cout_total_eur`, `date_simulee`. `vehicles` est un entier ≥ 0, égal à 100 par défaut. |
| `/api/indices` | Objet contenant `date_simulee` et `indices`, dictionnaire des neuf valeurs courantes. |

Champs de chaque composant renvoyé par les deux routes prix :
`id`, `nom`, `prix_unitaire_base_eur`, `prix_unitaire_actuel_eur`,
`variation_pct`, `quantite`, `cout_par_voiture_eur`.
`variation_pct` est la variation par rapport au prix de base, en pourcentage
(`"5"` signifie +5 %). `quantite` est la quantité pour une voiture.

Pour la production, `cout_production_eur` exclut le SAV ; `cout_stock_sav_eur`
est son supplément et `cout_total_eur` est leur somme. Utiliser les totaux
retournés par le backend sans recalculer les règles métier côté client.

```bash
curl http://localhost:8000/api/prices/BOM-0003
curl http://localhost:8000/api/vehicle-cost
curl 'http://localhost:8000/api/production-cost?vehicles=100'
```

Erreurs utiles : **404** avec le code `COMPONENT_NOT_FOUND` pour un ID inconnu ;
**422** pour un nombre de voitures invalide ; **503** avec un message mentionnant
`CARCOST_PRICE_BOM` si la simulation n'est pas configurée. Un chemin de fichier
inaccessible ou des données invalides empêchent le démarrage.
