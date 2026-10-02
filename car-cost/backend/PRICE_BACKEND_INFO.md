# Dynamic Pricing Backend

## Endpoint unique

```http
GET /api/prices?model={model}
```

| Valeur exacte de `model` | Fichier chargé au démarrage | Lignes |
|---|---|---:|
| `hybride` | `aston_martin_valhalla_hybride_phev.json` | 635 |
| `thermique` | `aston_martin_valhalla_thermique.json` | 575 |
| `electrique` | `aston_martin_valhalla_electrique.json` | 514 |

Aucun alias (`essence`, `hybrid`, `electric`, etc.). Les composants d'un modèle
ne sont pas mélangés avec ceux des autres. Les variantes thermique et électrique
sont hypothétiques ; toutes les données et tous les indices sont synthétiques.

## Utiliser la réponse

La réponse est le **JSON complet** du modèle, avec `vehicule` et `categories`.
Les catégories imbriquées, IDs, descriptions, fournisseurs, unités, garanties et
quantités restent identiques au fichier source. Seuls quatre montants changent :

- `prix_unitaire.prix` : prix dynamique dans la devise d'origine ;
- `prix_unitaire.prix_eur` : prix dynamique en EUR ;
- `prix_final.prix` : prix unitaire dynamique × `quantite_totale` ;
- `prix_final.prix_eur` : prix unitaire dynamique EUR × `quantite_totale`.

Les montants retournés sont des **nombres JSON**, arrondis à deux décimales
(`ROUND_HALF_UP`), jamais des chaînes. Les calculs internes utilisent des décimaux
non arrondis : le prix final est calculé avant l'arrondi de sortie, donc il peut
différer de quelques centimes du produit du prix unitaire déjà affiché.
Un nombre JSON comme `108` est équivalent à `108.00` ; les zéros d'affichage sont
à la charge du client.

## SAV : utiliser les quantités fournies

Le fichier fournit `quantite`, `quantite_sav` et `quantite_totale`, avec
`quantite_totale = quantite + quantite_sav`. La garantie est informative.
Aucun taux, arrondi de quantité ou supplément automatique n'est appliqué.
Par exemple : quantité 4, SAV 1, total 5 et prix dynamique 120 donnent un prix
final de 600. Le champ `prix_final` est recalculé depuis le prix unitaire de base,
jamais depuis le prix final de la réponse précédente.

Pour les autres équipes :

- **ne pas recalculer les prix dans le frontend** ;
- **ne pas recalculer le SAV, ni appliquer +3 %** ;
- utiliser directement `quantite_totale` et `prix_final` ;
- changer uniquement `model` lorsque l'utilisateur choisit une motorisation.

## Simulation et polling

Une année de 365 jours dure **40 minutes réelles**, puis boucle. Les neuf indices
locaux (`cuivre`, `aluminium`, `acier`, `lithium`, `nickel`, `energie`, `transport`,
`semi_conducteurs`, `GBP_EUR`) sont interpolés linéairement entre les jours,
y compris du dernier au premier. Le calcul a lieu uniquement à la requête ;
il n'existe ni boucle permanente ni WebSocket.

```text
SPEED = (365 * 24 * 60 * 60) / (40 * 60)
temps_simule = ((time.time() - start_time) * SPEED) % (365 * 24 * 60 * 60)
variation_indice = indice_actuel / indice_initial - 1
facteur = 1 + somme(poids_driver * variation_indice)
prix_unitaire_dynamique = prix_unitaire_base * facteur
prix_final_dynamique = prix_unitaire_dynamique * quantite_totale
```

Les poids dépendent du type de pièce et totalisent 1. Le FX utilise la devise
fournisseur : poids GBP/EUR pour GBP, poids nul et autres poids renormalisés pour
EUR. Le même facteur s'applique aux prix de base d'origine et EUR fournis par
le fichier ; ce n'est pas une conversion au cours de change instantané.

Les trois BOM et l'historique sont lus une seule fois au démarrage puis gardés
en RAM. Aucun accès disque, réseau ni base pendant les GET. Chaque réponse est
une copie : les données de base restent immuables. L'horloge est commune aux
modèles ; changer de modèle ne nécessite aucun redémarrage. À temps identique,
les prix sont identiques quel que soit le nombre d'appels.

```javascript
const model = "hybride"; // ou "thermique", "electrique"
const response = await fetch(`/api/prices?model=${model}`);
if (!response.ok) throw new Error(`Pricing HTTP ${response.status}`);
const bom = await response.json();
console.log(bom.categories);
```

Le frontend peut refaire cet appel environ toutes les **5 secondes**. Plusieurs
prix peuvent alors changer, tandis que structure et quantités restent identiques.

## Démarrage et exemples

Depuis la racine du dépôt, dans un environnement où le backend est installé :

```bash
python -m uvicorn carcost.infrastructure.api.main:app --port 8000 --workers 1
```

Les trois JSON fournis sont inclus dans
`src/carcost/infrastructure/data/boms/`. Facultativement, pour utiliser un autre
dossier contenant ces trois mêmes noms :

```bash
export CARCOST_PRICE_BOM_DIR=/chemin/vers/les_trois_json
python -m uvicorn carcost.infrastructure.api.main:app --port 8000 --workers 1
```

L'ancienne variable `CARCOST_PRICE_BOM` n'est plus utilisée. Un redémarrage
recharge les fichiers et remet l'horloge à zéro. Garder un seul worker pour une
horloge commune. Documentation interactive : `http://127.0.0.1:8000/docs`.

```bash
curl 'http://127.0.0.1:8000/api/prices?model=hybride'
curl 'http://127.0.0.1:8000/api/prices?model=thermique'
curl 'http://127.0.0.1:8000/api/prices?model=electrique'
```

Modèle absent : **422**. Modèle inconnu : **400**, avec
`{"detail":"Unknown model. Allowed values: hybride, thermique, electrique"}`.
Un fichier requis absent ou invalide empêche le démarrage.
Les anciennes routes `/api/prices/{component_id}`, `/api/vehicle-cost`,
`/api/production-cost` et `/api/indices` sont supprimées. Les routes historiques
`/api/v1/...` du projet restent inchangées.
