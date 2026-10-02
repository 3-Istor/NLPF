# ADR-0014 — Simulation locale des prix Valhalla

- **Date** : 2026-10-02
- **Statut** : proposé, actualisé selon le nouveau contrat demandé sur `prix`

## Décision

Une seule route pricing : `GET /api/prices?model=hybride|thermique|electrique`.
Les trois fichiers fournis sont conservés tels quels dans les données du paquet
backend, lus une fois au démarrage, validés puis figés récursivement en mémoire.
`CARCOST_PRICE_BOM_DIR` permet de choisir un autre dossier contenant les mêmes
noms de fichiers. Les historiques sont chargés une seule fois et l'horloge est
commune aux trois modèles. Aucun accès réseau, disque ou base pendant un GET.

La réponse copie la structure complète du modèle sélectionné. Seuls les montants
`prix` et `prix_eur` dans `prix_unitaire` et `prix_final` sont remplacés.
Le domaine calcule depuis les deux prix de base et le facteur pondéré existant ;
chaque prix final vaut son prix unitaire dynamique multiplié par la
`quantite_totale` fournie. `quantite + quantite_sav = quantite_totale` est validé
au chargement. La garantie est informative : aucun taux SAV ni plafond calculé.

Sur demande explicite, **ce contrat pricing uniquement** retourne les montants
en nombres JSON arrondis à deux décimales (`ROUND_HALF_UP`). Le calcul conserve
les `Decimal` non arrondis ; le prix final est calculé avant l'arrondi de sortie.
Cette exception à l'ADR-0011 n'affecte pas les API historiques ni le moteur DAG.
Les anciennes routes ajoutées pour la première simulation sont supprimées.

## Continuités et conséquences

Les neuf profils synthétiques et le traitement GBP/EUR sont conservés : poids FX
nul et autres poids renormalisés pour EUR, exposition GBP/EUR pour GBP. Le même
facteur de simulation s'applique aux deux prix de base fournis ; il ne s'agit pas
d'une conversion au cours de change instantané. Les valeurs ne sont pas des
prix constructeur. Les variantes thermique et électrique sont hypothétiques.

La simulation reste une année de 365 jours en 40 minutes, avec interpolation
linéaire jusqu'au retour du jour 364 au jour 0. Chaque requête échantillonne
l'horloge une fois. Le redémarrage remet le cycle à zéro ; utiliser un worker.
Aucune tâche périodique, dépendance ou persistance supplémentaire. Les routes
historiques et leurs adaptateurs ne sont pas modifiés.
