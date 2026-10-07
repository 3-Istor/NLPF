# price-api — l'API de prix simulée

Ce n'est pas le produit : c'est la source externe qu'il interroge (ADR-0003), écrite pour
pouvoir **tomber à la demande** et, depuis l'ADR-0015, pour **faire varier** les prix.
Bibliothèque standard seule.

```bash
python price-api/mock_price_api.py --port 8099 --year-minutes 40
```

- `GET /prices?refs=…&currency=EUR` — cotations à l'instant simulé ; pannes par l'en-tête
  `X-Mock-Failure: none | timeout | outlier | missing | garbage`.
- `GET /history?ref=…&currency=EUR` — les 365 jours simulés de la pièce qui finissent aujourd'hui, jour par jour.

Sans `--catalog`, il sert `seeds/price_catalog.json` (Multipla) et
`seeds/valhalla/*/price_catalog.json`. `--year-minutes 0` fige chaque prix à sa référence.

`simulation.py` : neuf indices synthétiques sur 365 jours (`data/price_indices.json`,
régénéré par `python -m tools.price_history`), interpolés entre deux jours et bouclés.
`prix = référence × (1 + Σ poids × variation de l'indice + part propre)` ; la part propre,
tirée d'une graine dérivée de la référence, fait varier chaque pièce à sa façon (nulle au
jour 0). La courbe est ensuite étirée pour aller de `year_min` à `year_max` du catalogue,
en partant de la référence au jour 0. Les poids (`drivers`) sont écrits
dans le catalogue à la génération du jeu de données. Le cours GBP→EUR ne s'applique qu'à la
devise que le fournisseur ne facture pas : un fournisseur britannique garde son prix en livres.

Toutes les valeurs sont **synthétiques**.
