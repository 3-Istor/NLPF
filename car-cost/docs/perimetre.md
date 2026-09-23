# Périmètre — 3istor

- **Date** : 2026-09-22
- **Statut** : proposé — en attente de validation humaine (point d'arrêt étape 2)
- **Entrée** : [cadrage.md](cadrage.md) validé le 2026-09-22

---

## 0. Décisions actées à la validation du cadrage

| Réf | Décision | Conséquence directe |
|---|---|---|
| **D1** | L'outil **montre** l'effet coût/CO₂ d'un changement fait par l'utilisateur. Il ne cherche pas la meilleure combinaison. | L'optimiseur passe en **Reporté** (§3). Le moteur reste une fonction pure appelable N fois, pour ne pas le bloquer plus tard. |
| **D2** | Coût = **quantité × coût unitaire**, le coût unitaire étant **matière + main-d'œuvre + règles**. | Modèle de coût figé (§0.1). Frais généraux, outillage, douane, marge restent **hors périmètre**. |
| **D3** | Portée d'un paramètre : **les deux, l'utilisateur choisit** (pièce ou chemin). | Objet de l'ADR-0002. La portée est un champ du modèle de scénario **dès la première ligne de code**, même quand une seule des deux est implémentée (§4). |
| **D4** | Scénarios et calculs **persistés en base, rechargeables**. | Rend l'invariant I5 démontrable. Le schéma porte scénario, snapshot et calcul dès la première migration. |
| **D5** | Le jeu de données Multipla est **à produire**. | Livrable de l'étape 4, avant le moteur. |

### 0.1 Le modèle de coût, écrit noir sur blanc

Sur une pièce **achetée** (`purchased`, feuille du graphe) :

```
coût unitaire = prix du snapshot (devise d'achat) × multiplicateur du fournisseur
contribution  = quantité × coût unitaire
```

Sur un ensemble **fabriqué** (`manufactured`, aucun prix propre) :

```
coût unitaire = Σ (quantité d'arête × coût unitaire de l'enfant)   ← la matière
              + (minutes de main-d'œuvre ÷ 60) × taux horaire      ← la main-d'œuvre
contribution  = quantité × coût unitaire
```

Les **règles** sont des modificateurs explicites, activables, listés dans les hypothèses de chaque
calcul. Deux règles seulement en v1 — voir la décision manquante **M2**, je n'en invente pas
d'autres :

- `labour` — inclure ou exclure la main-d'œuvre (permet de lire le coût matière seul) ;
- `supplier_multiplier` — appliquer ou ignorer le multiplicateur fournisseur (permet d'isoler
  l'effet du sourcing).

L'empreinte carbone suit exactement la même structure, avec le facteur carbone à la place du prix et
le CO₂ de transport du fournisseur à la place du multiplicateur. **Même parcours, mêmes quantités
cumulées, même explication** — c'est ce qui garantit que les deux chiffres se recoupent.

---

## 1. Dans le périmètre

### Jeu de données et graphe

1. **BOM exhaustive de la Multipla 1.6 16V** : ≥ 350 pièces, ≥ 5 niveaux, ≥ 40 pièces à parents
   multiples, racine unique, aucun orphelin, aucune arête doublée.
2. **Générateur déterministe** : deux exécutions produisent des fichiers identiques au bit près, et
   le générateur imprime son rapport de validation.
3. **Contrôles d'intégrité refusant le fichier** : cycle, racine multiple, orphelin, arête doublée,
   nœud acheté avec enfants, nœud fabriqué avec un prix propre.
4. **Catalogue de prix** en EUR, USD et RUB, avec référence et min/max annuels ; **fournisseurs**
   (2 à 3 par pièce achetée) avec origine, multiplicateur, délai et CO₂ de transport.
5. **Valeurs de contrôle** : la quantité cumulée de chaque pièce est stockée dans le jeu de données
   et sert de cas de test au moteur.

### Calcul

6. **Moteur de coût sur DAG** en programmation dynamique, en ordre topologique, chaque pièce évaluée
   une seule fois.
7. **Quantités cumulées** sommées sur tous les chemins.
8. **Deux vues d'explication** : agrégée (une ligne par pièce) et par occurrence (une ligne par
   chemin), dont la somme des contributions égale le total dans les deux cas.
9. **Empreinte carbone** produite par le même parcours que le coût.
10. **Scénario** : paramètres par pièce ou par chemin (fournisseur, devise d'achat, prix forcé
    justifié, temps de main-d'œuvre, règles actives), persisté et rechargeable.
11. **Calcul persisté** avec versions de BOM, de snapshot, de règles, horodatage et devise —
    rejouable au centime.
12. **Comparaison de deux fournisseurs pour une pièce donnée** : delta en euros, en pourcentage et
    en kg CO₂e. C'est ce qui fait de l'outil un outil de décision et pas un afficheur.

### Prix

13. **Mock API de prix** avec les trois pannes **déclenchables à la demande** : timeout, valeur
    aberrante, prix manquant.
14. **Snapshot de prix** immuable, horodaté, avec statut (`FRESH` / `STALE` / `DEGRADED`) et âge.
15. **Quarantaine** des valeurs aberrantes, journalisée et consultable (valeur rejetée, motif,
    valeur retenue à la place).

### Écran

16. **Arbre dépliable nœud par nœud**, de la racine à la vis, **chargement des enfants directs
    uniquement**.
17. **Badge « utilisée à N endroits »** sur les pièces partagées, menant à la vue *where-used*.
18. **Panneau de saisie contextuel** dans le nœud, différent selon le mode de valorisation, avec la
    **portée du réglage affichée explicitement**.
19. **Marquage visuel** du nœud modifié et de toute sa remontée jusqu'à la racine.
20. **Synthèse permanente** : total, CO₂, décomposition par système en valeur et en pourcentage,
    principaux contributeurs cliquables, snapshot utilisé avec son âge, état du calcul.
21. **Recherche** par référence ou libellé, dépliant automatiquement le chemin jusqu'à la pièce.
22. **État du calcul explicite** : à jour · paramètres modifiés depuis le dernier calcul · calcul en
    cours · échec. Aucun total périmé affiché comme frais.

### Qualité (livrables, pas intentions)

23. **Test de dépendance des couches** : le domaine n'importe ni `fastapi`, ni `sqlalchemy`, ni
    `httpx`.
24. **Fixture DAG en losange** et **test de non-réévaluation** par compteur d'appels.
25. **ADR** des neuf décisions structurantes, écrits au moment de la décision.

---

## 2. Hors périmètre

Une capacité listée ici ne sera pas construite, et on ne laisse pas de crochet « au cas où ».

| # | Exclu | Pourquoi |
|---|---|---|
| 1 | **Optimisation automatique** de la combinaison fournisseurs | D1. Problème combinatoire sur ~350 nœuds ; mangerait une soutenance sans rien démontrer sur le DAG. Voir §3.1 |
| 2 | **Authentification, comptes, rôles, multi-utilisateur** | Aucun besoin métier exprimé ; toucherait toutes les routes pour zéro question métier traitée |
| 3 | **Variantes et options du véhicule** (arêtes conditionnelles, dates d'applicabilité) | Une seule configuration de référence. Les arêtes conditionnelles doublent la complexité du parcours |
| 4 | **Édition de la nomenclature depuis l'interface** (créer/supprimer pièces et arêtes) | La BOM vient du seed et est en lecture seule. L'écriture impose la validation d'acyclicité en transaction : coût réel, aucune question métier du §3 du cadrage |
| 5 | **Import Excel, connecteur PLM/ERP** | L'outil remplace le classeur, il ne dialogue pas avec lui |
| 6 | **Frais généraux, amortissement d'outillage, douane, incoterms, marge** | D2 : le coût s'arrête à matière + main-d'œuvre + règles |
| 7 | **Taux de rebut et chutes de matière** | Aucune donnée de rebut, et en inventer fausserait tous les totaux |
| 8 | **Données constructeur réelles** (prix, masses, facteurs ADEME) | Non disponibles. Les données sont synthétiques et le disent dans leurs métadonnées |
| 9 | **Taux de change temps réel** | Le catalogue porte trois devises indépendantes ; un taux lu à l'exécution casserait la reproductibilité |
| 10 | **Versionnement de la BOM avec diff entre versions** | Une version figée suffit aux cinq questions ; on stocke l'identifiant de version, pas l'historique |
| 11 | **Export PDF / Excel des résultats** | Ne répond à aucune des cinq questions. Voir §3.3 |
| 12 | **Internationalisation de l'interface** | Français uniquement |
| 13 | **Application mobile / responsive avancé** | Écran étroit = synthèse en bandeau supérieur, rien de plus |
| 14 | **Collaboration temps réel** (websockets, curseurs partagés) | Un seul utilisateur à la fois |
| 15 | **Déploiement production, CI/CD complet, supervision, alerting** | Projet étudiant ; `docker compose` et des tests qui passent suffisent |
| 16 | **Calcul de délai d'approvisionnement / chemin critique** | Le délai est stocké et affiché, jamais agrégé. L'agrégation est un autre problème (chemin critique), pas une extension du coût |
| 17 | **Gestion de stock, approvisionnement, MRP** | Autre métier |
| 18 | **Recalcul incrémental** du sous-graphe impacté | Optimisation prématurée tant que le recalcul complet est imperceptible. Voir §3.4 |
| 19 | **Annuler / rétablir** sur les paramètres | Confort ; le scénario persisté et rechargeable couvre le besoin réel |
| 20 | **Balayage de sensibilité automatique** sur toutes les pièces | La comparaison fournisseur pièce par pièce (§1.12) répond à Q3. Le balayage est un pas vers l'optimiseur exclu en 1. Voir §3.2 |

---

## 3. Reporté

Souhaitable, pas maintenant. Chacun porte le **signal observable** qui rouvre le débat.

### 3.1 Optimiseur de combinaison fournisseurs
*Déclencheur* : les tranches T1 à T3 passent leurs tests **et** un calcul complet tient sous la
seconde **et** le besoin est reformulé explicitement (« propose-moi la meilleure combinaison sous
contrainte de X kg CO₂e »).
*Ce qu'on préserve pour ne pas se fermer la porte* (D1) : le moteur reste une fonction pure
`(BOM, scénario, snapshot) → résultat`, sans état, appelable en boucle.

### 3.2 Analyse de sensibilité multi-pièces (top N des pièces les plus sensibles)
*Déclencheur* : la comparaison pièce par pièce est jugée trop laborieuse en usage réel, sur un
scénario documenté.

### 3.3 Export de l'explication (CSV, puis PDF)
*Déclencheur* : première demande de partage du résultat hors de l'outil.

### 3.4 Recalcul incrémental
*Déclencheur* : le recalcul complet dépasse **2 s** mesurées sur la BOM réelle.

### 3.5 Comparaison de deux scénarios enregistrés (« qu'est-ce qui a changé depuis lundi ? »)
*Déclencheur* : deux scénarios persistés coexistent et la question est posée. C'est la sixième
question métier laissée de côté au cadrage.

### 3.6 Portée « chemin » exposée dans l'interface
*Déclencheur* : **fin de la tranche T2** — c'est un report de calendrier, pas de périmètre. D3 est
acté : le modèle porte la portée dès T1 (§4).

---

## 4. La tranche verticale minimale

### Le scénario de démonstration, en une phrase

On ouvre la Multipla, on descend de la racine jusqu'à une vis partagée, on voit qu'elle est employée
à douze endroits, on change son fournisseur, les totaux passent en « obsolète », on recalcule, et le
nouveau total est explicable jusqu'au prix unitaire de cette vis et à la date du snapshot qui l'a
fournie.

C'est étroit, et c'est le but : **tout le reste du périmètre §1 est un élargissement de ce chemin,
pas un autre chemin.**

### Ce que T1 contient délibérément *moins* que le périmètre

| Volontairement absent de T1 | Arrive en |
|---|---|
| Empreinte carbone | T2 |
| Devises USD / RUB (T1 est en EUR) | T2 |
| Pannes P2 (quarantaine) et P3 (prix manquant) — T1 traite le nominal et le timeout | T2 |
| Portée « chemin » **exposée à l'écran** (le champ existe, seule la portée pièce est résolue) | T2 |
| Prix forcé, temps de main-d'œuvre éditable, recherche, vue par occurrence | T2 |
| Comparaison de fournisseurs avec delta | T3 |

La BOM, elle, est **complète dès T1**. Développer contre un extrait de vingt pièces reviendrait à
écrire le moteur contre des données jouets — précisément ce que l'étape 4 existe pour éviter.

### Les étapes, dans l'ordre

| # | Étape | Livrable | Critère de sortie (démontrable) |
|---|---|---|---|
| **1** | **Jeu de données** | `seeds/bom_multipla.json`, `parts.csv`, `edges.csv`, `price_catalog.json`, `suppliers.json`, générateur déterministe | Rapport de validation à **zéro erreur** : ≥ 350 pièces, ≥ 5 niveaux, ≥ 40 pièces multi-parents, racine unique, acyclicité par tri topologique. Deux exécutions donnent des fichiers identiques |
| **2** | **Schéma et chargement** | Migration versionnée (pièces, **table d'arêtes**, fournisseurs, snapshots, scénarios, calculs) + chargement `COPY` | Les compteurs en base correspondent au rapport de l'étape 1. Les contraintes d'intégrité rejettent une arête doublée |
| **3** | **Moteur de coût** (domaine pur) | DP en ordre topologique, quantités cumulées, contributions, vue agrégée | **Test d'abord** : fixture DAG en losange avec des quantités ≠ 1, rouge puis vert. Les valeurs de contrôle de la BOM réelle passent. Le compteur d'appels prouve une évaluation unique par pièce. Le test de dépendance des couches passe |
| **4** | **Prix : snapshot et mock API** | Mock API, prise de snapshot immuable, repli sur timeout, statut et âge | Nominal → `FRESH`. Timeout forcé → `DEGRADED` + snapshot de repli identifié, **jamais** d'erreur 500 |
| **5** | **API de lecture du graphe** | `GET /bom/{version}/root`, `GET /nodes/{id}/children`, `GET /parts/{ref}/where-used` | Déplier un nœud renvoie **ses enfants directs et rien d'autre** ; chaque enfant porte son compte de parents |
| **6** | **API de calcul** | `POST /calculations` (scénario → calcul persisté), `GET /calculations/{id}` avec total, décomposition par système et contributeurs | Deux appels identiques → **même résultat au centime**. La somme des contributions égale le total. La somme des systèmes égale le total |
| **7** | **Écran : arbre + synthèse** | Arbre à dépliage paresseux, badge « utilisée à N endroits », where-used, synthèse toujours visible avec snapshot et âge | On descend de la racine à une vis par dépliages successifs ; l'onglet réseau montre **un appel par dépliage**, jamais le graphe entier |
| **8** | **Écran : saisie, obsolescence, recalcul** | Panneau contextuel (achat ≠ fabrication), portée affichée, marquage du nœud et de sa remontée, bouton de recalcul | Changer le fournisseur marque le nœud et ses parents, fait passer les totaux en **obsolète**, et après recalcul le total affiché est **exactement** celui de l'API. Aucun calcul arithmétique métier dans le navigateur |

**Règle de progression** : on ne commence pas une étape avant que la précédente passe ses tests. Une
étape qui passe est commitée seule, avec un message à l'impératif.

### Après T1

- **T2 — « L'outil dit la vérité sur ses prix »** : pannes P2 et P3, carbone, devises, portée chemin
  exposée, prix forcé justifié, recherche, vue par occurrence.
- **T3 — « L'outil aide à décider »** : comparaison de fournisseurs avec delta coût et CO₂ (Q3 et
  Q5), contributeurs carbone.

Une seule tranche complète vaut mieux que trois entamées : si le temps manque, **T3 saute**, T1 et T2
restent une démonstration crédible.

---

## 5. Décisions manquantes (voir la réponse accompagnant ce document)

- **M1** — La provenance est-elle un champ indépendant du fournisseur ?
- **M2** — Le catalogue des règles activables se limite-t-il aux deux règles du §0.1 ?
