# Cadrage — 3istor, outil d'aide à la décision sur le coût de fabrication

- **Date** : 2026-09-22
- **Statut** : proposé — en attente de validation humaine (point d'arrêt étape 1)
- **Véhicule de référence** : Fiat Multipla 1.6 16V
- **Relation avec l'existant** : ce document reprend, précise et étend [besoins.md](besoins.md)
  (Raphael Ye, 2026-09-19). Les écarts assumés sont listés au §7. `besoins.md` reste dans le dépôt :
  il porte le raisonnement d'origine.

---

## 1. Le problème, en cinq lignes

Le coût de fabrication de la Multipla est aujourd'hui calculé dans un classeur de 300 Mo que plus
personne n'ouvre sans le faire tomber, et surtout que personne ne peut auditer : on y lit un total,
jamais son origine. Nous le remplaçons par un outil qui, à partir de la nomenclature du véhicule et
de paramètres saisis pièce par pièce (fournisseur, provenance, devise), renvoie un coût de
fabrication et une empreinte carbone. La difficulté n'est pas l'addition : une nomenclature n'est pas
un arbre — la même vis M6 est montée sous le moteur *et* sous la caisse — et les prix viennent d'une
API externe qui tombe. Un total qu'on ne peut ni décomposer jusqu'au prix unitaire d'une pièce, ni
rejouer à l'identique trois mois plus tard, n'a aucune valeur de décision. L'outil sera donc jugé sur
trois choses : la justesse des quantités cumulées sur le graphe, la traçabilité de chaque euro, et
l'honnêteté affichée quand les prix sont dégradés.

---

## 2. Acteurs et attentes

| Acteur | Ce qu'il fait avec l'outil | Ce qu'il attend | Ce qui le ferait revenir à Excel |
|---|---|---|---|
| **Chiffreur** (utilisateur principal) | Ouvre la nomenclature, règle des paramètres sur des pièces, relance le calcul, compare des hypothèses | Un total qu'il peut défendre ligne à ligne devant un tiers | Un chiffre qu'il ne peut pas justifier, ou qui change sans qu'on sache pourquoi |
| **Acheteur / sourcing** | Teste des fournisseurs et des origines sur les pièces sensibles | Savoir quelle pièce fait le plus bouger le total, et sur combien d'endroits du véhicule son réglage s'applique | Un outil qui ne dit pas si son changement vaut pour une occurrence ou pour les douze |
| **Responsable carbone** | Lit l'empreinte, ses contributeurs, l'effet d'un fournisseur plus proche | Une empreinte calculée sur la même nomenclature et le même calcul que le coût | Deux chiffres issus de deux sources qui ne se recoupent pas |
| **Gestionnaire de nomenclature (BE)** | Fournit et corrige la BOM | Que l'outil **refuse** une nomenclature incohérente (cycle, orphelin, prix posé sur un ensemble) au lieu de la digérer en silence | Un import qui accepte tout et produit un total faux |
| **Direction / auditeur** | Demande « d'où sort ce chiffre ? » sur un calcul d'il y a trois mois | Le rejouer au centime, avec les prix de l'époque | Un total non reproductible |
| **Jury de soutenance** | Lit le dépôt autant que l'écran | Des décisions tracées, y compris les chemins non pris | Un squelette de projet et des données jouets |
| **API de prix** (acteur système, simulée) | Fournit des prix, tombe, renvoie des valeurs aberrantes | — | — |
| **Équipe (4 personnes, 2 soutenances)** | Construit | Une tranche verticale finie plutôt que quatre couches à moitié | — |

---

## 3. Cinq questions auxquelles l'outil doit savoir répondre

Formulées du point de vue de l'utilisateur métier. Chacune porte son critère d'acceptation : la
question est traitée le jour où ce critère est vérifiable à l'écran.

**Q1 — « Combien coûte la fabrication de cette voiture, et avec quels prix ? »**
Le total dans la devise d'affichage, accompagné de l'identifiant du snapshot de prix, de son
horodatage, de son âge, et d'un marqueur s'il est dégradé.
*Acceptation* : le total affiché est exactement celui renvoyé par l'API, au centime, et l'âge du
snapshot est visible en permanence.

**Q2 — « Où part l'argent ? »**
La décomposition par grand système (motopropulseur, châssis, carrosserie, intérieur, électricité,
fluides…) en valeur et en pourcentage, puis les principaux contributeurs pièce par pièce, cliquables
jusqu'à la pièce dans l'arbre.
*Acceptation* : la somme des systèmes égale le total affiché ; un clic sur un contributeur déplie le
chemin jusqu'à lui.

**Q3 — « Quelle pièce fait le plus varier le coût total si je change de fournisseur ? »**
Pour une pièce donnée, l'écart de total entre deux fournisseurs, en euros et en pourcentage, avec la
portée du changement affichée explicitement (toutes les occurrences, ou seulement celle-ci).
*Acceptation* : le delta annoncé avant recalcul correspond au total obtenu après recalcul.

**Q4 — « Cette pièce, combien y en a-t-il en tout dans la voiture, et où est-elle montée ? »**
La quantité cumulée sur tous les chemins (la vis n'est pas comptée une fois parce qu'elle apparaît
une fois à l'écran), et la liste des chemins d'utilisation (*where-used*).
*Acceptation* : sur la BOM réelle, les quantités cumulées calculées correspondent aux valeurs de
contrôle du jeu de données (le pneumatique à 5, roue de secours comprise ; la vitre de porte à 2 ;
les segments d'attelage à 12).

**Q5 — « Quelle est l'empreinte carbone, qui la porte, et combien me coûte le fait de la réduire ? »**
L'empreinte totale en kg CO₂e, ses principaux contributeurs, et, pour un changement de fournisseur
donné, l'effet simultané sur le coût et sur le CO₂ — de façon à voir l'arbitrage, pas à le subir.
*Acceptation* : un même recalcul produit les deux chiffres ; ils reposent sur la même nomenclature et
les mêmes quantités cumulées.

> Une sixième question est candidate et volontairement laissée à l'étape 2 : **« qu'est-ce qui a
> changé entre mon chiffrage de lundi et celui d'aujourd'hui ? »** Elle suppose la persistance et la
> comparaison de deux calculs enregistrés. Utile, mais non nécessaire à la tranche verticale
> minimale — voir §6, ambiguïté A7.

---

## 4. Cinq invariants non négociables

Un invariant est une propriété qui doit rester vraie quelles que soient les données, les paramètres
et l'état de l'API. Chacun est formulé pour être **vérifiable par un test**, pas pour être respecté
par discipline.

### I1 — Conservation : la somme des contributions égale le total

Dans les deux vues — agrégée (une ligne par pièce, quantité cumulée) et par occurrence (une ligne par
chemin) — la somme des contributions est égale au total, au centime.
*Vérification* : test de propriété sur la BOM réelle et sur les fixtures.
*Sans lui* : l'outil produit un total que sa propre décomposition contredit ; il n'est plus
explicable, donc plus utilisable pour décider.
*Dépendance* : impose de trancher la règle d'arrondi (§6, A3) — un arrondi par ligne et un arrondi au
total ne donnent pas le même résultat.

### I2 — Valorisation exclusive : jamais de double comptabilisation

Une pièce a un mode de valorisation et un seul. `purchased` : le coût est le prix d'achat, le nœud
est une **feuille** et n'a aucun enfant. `manufactured` : le coût est la somme des enfants plus la
main-d'œuvre, et le nœud **n'a pas** de prix propre.
*Vérification* : refus à l'import (un nœud acheté avec des enfants, ou un nœud fabriqué avec un prix,
fait échouer la validation du jeu de données) ; test unitaire côté moteur.
*Sans lui* : on double le coût d'un ensemble (prix propre + enfants) ou on le perd entièrement
(fabriqué dont les enfants ne sont pas sommés).

### I3 — Structure : le graphe reste un DAG à racine unique

La BOM est un graphe orienté **acyclique**, à racine unique, sans arête dupliquée (une paire
parent-enfant est unique) et sans nœud orphelin (toute pièce déclarée est employée quelque part).
*Vérification* : tri topologique explicite à l'import et refus de toute écriture qui créerait un
cycle — l'acyclicité est **contrôlée, pas supposée**.
*Sans lui* : le calcul ne termine pas, ou termine sur un résultat arbitraire selon l'ordre de
parcours.

### I4 — Quantité cumulée : somme sur tous les chemins

La quantité cumulée d'une pièce dans le véhicule est la somme, sur **tous** les chemins de la racine
à cette pièce, du produit des quantités d'arêtes. Une pièce partagée n'est ni comptée une seule fois,
ni comptée en double.
*Vérification* : les valeurs de contrôle du jeu de données sont les cas de test du moteur ; au moins
une est vérifiable à la main.
*Sans lui* : le moteur traite le DAG comme un arbre et sous-compte tout ce qui est partagé —
précisément l'erreur que l'outil existe pour éviter.

### I5 — Un résultat est toujours daté, sourcé et rejouable

Tout calcul enregistre les versions de nomenclature, de prix, de règles, son horodatage et sa devise.
Mêmes entrées + même snapshot ⇒ même résultat, au centime. Un snapshot et un calcul enregistrés ne
sont **jamais** modifiés rétroactivement. Tout montant affiché remonte à sa source (prix unitaire,
fournisseur, snapshot), et un résultat dégradé, incomplet ou périmé est **étiqueté comme tel** — y
compris lorsque des paramètres ont été modifiés depuis le dernier calcul.
*Vérification* : test de reproductibilité (deux exécutions sur le même snapshot) ; test d'immuabilité
(aucune écriture sur un snapshot existant) ; l'état du calcul est une donnée renvoyée par l'API, pas
une décoration du front.
*Sans lui* : un chiffre frais et un chiffre périmé sont indiscernables à l'écran, ce qui est pire que
pas de chiffre du tout.

---

## 5. Trois modes de panne de l'API de prix

Principe commun : **jamais de plantage, jamais de silence, jamais de zéro inventé.** Le calcul aboutit
ou déclare précisément ce qui lui manque.

### P1 — L'API ne répond pas (timeout, erreur réseau, 5xx)

*Détection* : dépassement du budget de temps par appel, ou erreur de transport. Les appels échoués
sont comptabilisés ; au-delà d'un seuil, on cesse d'insister (coupe-circuit) au lieu d'empiler les
timeouts.
*Réaction* : repli sur le **dernier snapshot valide**. Le calcul aboutit et est marqué `DEGRADED`.
*Ce que voit l'utilisateur* : le total est produit, accompagné de l'identifiant du snapshot de repli,
de son horodatage et de son âge ; le marqueur « dégradé » est visible sur le total **et** sur les
lignes concernées.
*Interdit* : présenter le total comme frais, ou faire échouer l'écran entier.
*Test* : mock API en timeout → réponse `200` avec `status = DEGRADED` et snapshot de repli identifié.

### P2 — L'API répond une valeur aberrante

*Détection* : prix négatif, prix nul sur une pièce achetée, valeur non numérique, devise inconnue,
unité incohérente, ou écart au prix de référence au-delà d'un seuil (à fixer, §6 A5).
*Réaction* : la valeur est mise en **quarantaine** — elle n'entre pas dans le snapshot. On retombe sur
la dernière valeur saine connue **pour cette pièce**.
*Ce que voit l'utilisateur* : la ligne porte un marqueur « prix en quarantaine » avec la valeur
rejetée, la raison du rejet et la valeur utilisée à la place ; le journal de quarantaine est
consultable.
*Interdit* : intégrer silencieusement la valeur, ou la remplacer sans le dire.
*Test* : mock renvoyant `-42 EUR` puis `9 999 999 EUR` → snapshot inchangé, deux entrées de
quarantaine, total identique au calcul de référence.

### P3 — L'API répond, mais sans prix pour une pièce achetée

*Détection* : réponse partielle — pièce absente de la réponse, ou prix `null`.
*Réaction* : dernier prix connu pour cette pièce. **Si aucun prix connu n'existe**, la pièce est
déclarée non valorisable : le calcul produit le sous-total des pièces valorisables et marque le
résultat `INCOMPLETE`, en listant nommément les pièces sans prix.
*Ce que voit l'utilisateur* : un total explicitement incomplet, jamais un total présenté comme
complet ; la liste des pièces manquantes est cliquable jusqu'à leur position dans l'arbre.
*Interdit* : substituer `0` (qui minore le total sans que rien ne le signale), interpoler, ou
extrapoler depuis une pièce voisine.
*Test* : mock omettant une pièce sans historique → `status = INCOMPLETE`, pièce listée, total partiel
et marqué.

> Les trois pannes sont provoquées à la demande dans la mock API (paramètre de scénario), pour que la
> démonstration ne dépende pas du hasard.

---

## 6. Zones d'ambiguïté

Ce que l'énoncé ne dit pas et qui change la conception selon la réponse. La colonne « hypothèse de
travail » indique ce que nous appliquerons **faute de réponse** — elle sera signalée dans le code et
dans les ADR, jamais appliquée en silence.

| # | Question ouverte | Ce qui change selon la réponse | Hypothèse de travail par défaut | Coût de se tromper |
|---|---|---|---|---|
| **A1** | « Cette vis vient du fournisseur X » vaut-il pour **toutes** les occurrences de la vis, ou seulement sous un sous-ensemble donné ? | Modèle de scénario, clé de mémoïsation, complexité du calcul, libellés de l'écran | Portée **pièce** par défaut ; portée **chemin** proposée seulement là où elle a un sens métier | Portée chemin partout : la mémoïsation saute et le calcul peut exploser. Objet de l'ADR-0002, à trancher avant le modèle |
| **A2** | Que recouvre exactement « coût de fabrication » ? Matière + main-d'œuvre, ou aussi frais généraux, amortissement d'outillage, transport, douane, marge ? | Le modèle de coût lui-même, donc tous les chiffres produits | **Matière + main-d'œuvre uniquement**. L'effet du sourcing passe par le multiplicateur de prix du fournisseur, pas par une ligne de transport séparée | Ajouter les frais généraux après coup change tous les totaux et invalide les captures de soutenance |
| **A3** | Arrondi : à la ligne ou au total ? Quelle règle (`ROUND_HALF_UP` ?) ? Quelle précision interne ? | La validité de l'invariant I1, au centime | Calcul interne en décimal exact, **arrondi au dernier moment**, `ROUND_HALF_UP`, 2 décimales à l'affichage | Un arrondi par ligne fait diverger la somme des contributions du total : I1 tombe |
| **A4** | Main-d'œuvre : un taux horaire unique, un taux par atelier, ou un taux par pays d'assemblage ? | Le modèle de règles de coût et le panneau de saisie des nœuds fabriqués | **Un taux horaire unique**, paramétrable globalement, affiché dans les hypothèses du calcul | Un taux par pays introduit une deuxième dimension de sourcing non prévue au modèle |
| **A5** | Quand un prix est-il « aberrant » ? Quel seuil d'écart au prix de référence déclenche la quarantaine ? | Le comportement P2, donc le nombre de faux positifs en démonstration | Hors de l'intervalle `[min, max]` annuel du catalogue, ou écart > 50 % au prix de référence | Seuil trop serré : tout part en quarantaine et l'outil paraît cassé. Trop lâche : il avale n'importe quoi |
| **A6** | Durée de vie d'un snapshot : au bout de combien de temps est-il « périmé » ? Un snapshot périmé bloque-t-il le calcul ou le marque-t-il seulement ? | Le comportement P1 et l'affichage permanent de l'âge | **24 h** avant d'être marqué périmé ; un snapshot périmé **n'empêche pas** le calcul, il le marque | S'il bloque, une coupure d'API d'une journée rend l'outil inutilisable ; s'il ne marque rien, on décide sur des prix morts |
| **A7** | Les scénarios sont-ils **enregistrés** (nommés, rechargés, comparés) ou vivent-ils le temps d'une session ? | Le schéma de base, l'API, la faisabilité de « qu'est-ce qui a changé depuis lundi ? » | Scénario **persisté** (il est la clé de la reproductibilité I5) ; **comparaison de deux scénarios reportée** | Un scénario en mémoire seule rend I5 invérifiable en démonstration |
| **A8** | Y a-t-il plusieurs utilisateurs, avec authentification et droits ? | Le schéma, l'API, et la traçabilité du « prix forcé à justifier » | **Mono-utilisateur, sans authentification** ; le prix forcé exige une justification textuelle obligatoire, horodatée, stockée avec le scénario | Ajouter l'authentification tard touche toutes les routes |
| **A9** | Gère-t-on des **variantes** du véhicule (options, motorisations, finitions) ? | Le modèle d'arêtes (conditions d'applicabilité) et l'interface | **Non** : une seule configuration, la Multipla 1.6 16V ; les variantes se simulent par paramètres, pas par arêtes conditionnelles | Les arêtes conditionnelles sont coûteuses à ajouter après coup |
| **A10** | Taux de rebut / chutes de matière ? Périmètre du facteur carbone (extraction → sortie d'usine ? usage ? fin de vie ?) | Les quantités matière et l'empreinte annoncée | **Pas de rebut** ; empreinte **de l'extraction à la sortie d'usine**, transport fournisseur inclus, usage et fin de vie exclus | Annoncer une empreinte sans dire son périmètre est une erreur de fond, pas de forme |
| **A11** | Devises : les trois devises du catalogue (EUR, USD, RUB) sont-elles des prix indépendants ou dérivées d'un taux ? Le taux est-il figé dans le snapshot ? | La reproductibilité I5 dès qu'on change de devise d'affichage | Prix **indépendants par devise** dans le catalogue ; tout taux de conversion utilisé est **figé dans le snapshot** | Un taux lu à l'exécution rend deux calculs identiques irreproductibles |

**Honnêteté des données** : prix, masses et facteurs carbone seront **plausibles mais synthétiques**.
Ce n'est pas une ambiguïté, c'est une contrainte : le jeu de données le déclarera dans ses
métadonnées et la documentation le répétera. Aucun chiffre de ce projet n'est une donnée
constructeur.

---

## 7. Écarts assumés avec `besoins.md`

| Point | `besoins.md` | Ici | Raison |
|---|---|---|---|
| Question 5 | « Quelle configuration permet de réduire le coût tout en maîtrisant l'empreinte ? » | Reformulée en arbitrage observé (Q5), pas en optimisation | Chercher *la* configuration optimale est un problème d'optimisation combinatoire sur un DAG — hors de portée en deux soutenances, et jamais demandé par l'énoncé |
| Invariants | Calculabilité, reproductibilité, cohérence, immuabilité, non-double-comptage | Conservation, valorisation exclusive, structure du DAG, quantité cumulée, résultat daté/sourcé/rejouable | Les invariants d'origine sont justes mais non testables tels quels ; ceux-ci sont formulés pour tomber dans un test. « Calculabilité » et « immuabilité » sont absorbées par I5 ; « cohérence » par I1 et I4 |
| Structure du graphe | Non traitée | I3 et I4 : le DAG est un fait de cadrage, pas un détail technique | Une pièce à plusieurs parents change le sens du mot « quantité » ; c'est du domaine, pas de l'implémentation |
| Ordre des pannes | Indisponible, manquant, invalide | Indisponible, **aberrant**, manquant | Aligné sur la réaction attendue : repli, quarantaine, résultat incomplet |

---

## 8. Ce que ce document n'engage pas

Le périmètre — ce que l'outil fera, ce qu'il ne fera pas, et la tranche verticale minimale — est
traité à l'étape suivante, dans `perimetre.md`. Les décisions d'architecture (modélisation de la BOM,
portée des paramètres, snapshot, découpage en couches, stratégie de calcul, mode de valorisation)
sont traitées en ADR, avant toute ligne de code.
