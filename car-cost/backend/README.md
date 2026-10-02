# Backend

La simulation Valhalla utilise le JSON fourni à son emplacement, sans copie.
Depuis la racine du dépôt, après installation du backend (`pip install -e 'car-cost/backend[dev]'`) :

```bash
CARCOST_PRICE_BOM=/home/joebuntu/Downloads/aston_martin_valhalla_bom_simple.json \
  python -m uvicorn carcost.infrastructure.api.main:app --port 8000 --workers 1
```

Les cinq routes `/api/prices`, `/api/prices/{id}`, `/api/vehicle-cost`,
`/api/production-cost?vehicles=100` et `/api/indices` calculent en RAM, sans
réseau ni base. Sans `CARCOST_PRICE_BOM` exportée, les routes prix répondent 503 avec un message
explicite. Sur deux lignes, utiliser `export CARCOST_PRICE_BOM=...` avant Uvicorn.
Les fichiers sont chargés une fois au démarrage ; redémarrer pour les recharger.
Une année de 365 jours dure 40 minutes, avec interpolation linéaire et bouclage
continu des indices. Un redémarrage remet la simulation à zéro.

Données et indices **synthétiques**, sans valeur de prix constructeur. Les
montants sont des chaînes décimales sans arrondi d'affichage. Les poids sont dans
`domain/price_drivers.py` ; le SAV majore uniquement les quantités sous garantie.
L'historique versionné se régénère hors serveur depuis `car-cost` avec
`python -m tools.price_history` (bibliothèque standard uniquement).
