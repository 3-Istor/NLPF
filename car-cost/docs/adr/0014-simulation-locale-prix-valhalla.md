# ADR-0014 — Simulation locale des prix Valhalla

- **Date** : 2026-10-02
- **Statut** : proposé

## Contexte et décision

La demande Valhalla impose une simulation sans réseau ni persistance, avec une
année en 40 minutes. Les routes FastAPI sont toujours enregistrées ; le chemin
`CARCOST_PRICE_BOM` active leur simulation (sinon réponse 503 explicite). Le fichier fourni reste à son emplacement, sans copie.
Les catégories imbriquées regroupent des lignes dont les quantités sont déjà
exprimées pour une voiture ; elles ne constituent pas les arêtes du DAG Multipla.

Le domaine calcule prix et quantités SAV en `Decimal`. L'application calcule
l'instant simulé une fois par requête. L'infrastructure charge et valide BOM et
365 observations par indice au démarrage. Aucune tâche périodique n'est créée.
Les données et indices sont synthétiques, sans prétention de prix constructeur.

## Options et conséquences

Étendre les snapshots PostgreSQL ajouterait une persistance contraire au besoin.
Remplacer le moteur DAG casserait son contrat : la simulation reste un cas
d'usage distinct, dans les mêmes couches et la même application FastAPI.
Les routes historiques conservent leurs adaptateurs ; les nouvelles routes
n'en dépendent pas. Le redémarrage réinitialise la simulation, commune aux
requêtes d'un processus : lancer un seul worker.

Les valeurs monétaires sont sérialisées en chaînes sans arrondi d'affichage.
Le SAV suit exclusivement `ceil(quantité × véhicules × 1.03)` pour les pièces
sous garantie ; le prix unitaire reste inchangé.

## Paramètres validés pour cette simulation

Les neuf profils du module `domain/price_drivers.py` reprennent les poids
fournis par le demandeur. Le libellé est classé avant la description, avec
priorité aux fixations pour ne pas confondre une vis et son organe de montage.
La devise fournisseur détermine le FX : GBP/EUR pour GBP, poids nul et
renormalisation proportionnelle des autres coefficients pour EUR.
Les matières plastiques et le caoutchouc utilisent l'indice énergie.

La position temporelle fournit directement la fraction de jour. Chaque indice
est interpolé linéairement entre deux observations ; le jour 364 rejoint le
jour 0 pour garantir la continuité au bouclage. La date repart du 1er janvier
2026, origine de l'historique synthétique. Aucun prix de base n'est réécrit.
