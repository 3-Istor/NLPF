# Backend

La simulation pricing Valhalla expose un seul endpoint :
`GET /api/prices?model=hybride|thermique|electrique`.
La réponse conserve la BOM complète et actualise uniquement ses prix.

Depuis la racine du dépôt, après installation des dépendances existantes :

```bash
python -m pip install -e 'car-cost/backend[dev]'
python -m uvicorn carcost.infrastructure.api.main:app --port 8000 --workers 1
```

Les trois BOM synthétiques sont incluses dans le paquet. La variable facultative
`CARCOST_PRICE_BOM_DIR` sélectionne un autre dossier avec les trois mêmes noms.
L'ancienne variable `CARCOST_PRICE_BOM` n'est plus utilisée.

Contrat, SAV fourni, polling et exemples : [PRICE_BACKEND_INFO.md](PRICE_BACKEND_INFO.md).
L'historique local se régénère hors serveur depuis `car-cost` avec
`python -m tools.price_history` (bibliothèque standard uniquement).
