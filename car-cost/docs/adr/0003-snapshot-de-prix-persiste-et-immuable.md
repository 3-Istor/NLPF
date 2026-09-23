# ADR-0003 — Le snapshot de prix est pris côté serveur, stocké en base, immuable et daté

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor — décision D4 (persistance), validée le 2026-09-22

## Contexte et problème

Les prix viennent d'une API externe qui tombe, renvoie des valeurs aberrantes ou incomplètes. Deux
exigences s'y ajoutent : un calcul doit être **rejouable à l'identique** des mois plus tard, et
l'utilisateur doit voir en permanence **avec quels prix** il travaille et **de quand** ils datent.

Il faut donc décider où vivent les prix entre l'API et le calcul, quand ils sont figés, et combien de
temps ils restent valides.

## Critères de décision

1. **Reproductibilité au centime**, y compris après que les prix du marché ont changé. *Décisif.*
2. Comportement en panne : le calcul doit aboutir ou dire précisément ce qui lui manque.
3. Fraîcheur perçue : l'utilisateur doit savoir si son chiffre est vieux.
4. Volume de stockage et complexité.

## Options envisagées

### Option A — Appel direct à l'API à chaque calcul, aucun stockage
Le moteur interroge l'API au moment du calcul.
*Apporte* : toujours le prix du moment, zéro stockage, aucune question de péremption.
*Coûte* : deux calculs identiques peuvent différer, et chaque calcul dépend de la disponibilité de
l'API.

### Option B — Snapshot persisté et immuable
Une **prise de snapshot** interroge l'API, valide les valeurs, met les aberrations en quarantaine et
écrit une photographie horodatée. Chaque calcul cite l'identifiant du snapshot qu'il a utilisé. Une
nouvelle prise crée un **nouveau** snapshot ; aucun n'est jamais modifié.
*Apporte* : reproductibilité, repli naturel en cas de panne, âge affichable, valeur citable devant
un auditeur.
*Coûte* : il faut décider quand prendre un snapshot, et l'utilisateur peut travailler sur des prix
vieux.

### Option C — Cache mémoire à durée de vie limitée dans le processus API
Les prix sont mis en cache avec un TTL.
*Apporte* : simple, rapide, absorbe les micro-pannes.
*Coûte* : disparaît au redémarrage, n'a pas d'identifiant, ne se raconte pas.

## Décision

**Option B.** Raison décisive : un calcul doit pouvoir être rejoué trois mois plus tard **avec les
prix de l'époque**. Seule une archive persistante et immuable le permet — un cache ou un appel direct
perdent l'information au premier redémarrage.

Règles retenues :
- un snapshot porte : identifiant, horodatage, source, les trois devises, un statut, et une ligne de
  prix par pièce achetée ;
- statut `FRESH` avant **24 h**, `STALE` au-delà, `DEGRADED` s'il a été construit par repli ou s'il
  est incomplet ;
- un snapshot `STALE` **n'empêche pas** le calcul : il le marque ;
- les valeurs rejetées vont dans un **journal de quarantaine** rattaché au snapshot, avec le motif et
  la valeur retenue à la place ;
- un snapshot n'est jamais modifié, jamais réparé, jamais complété.

## Hypothèses et options abandonnées

**Option A — appel direct, sans stockage**
- *Ce qu'elle proposait* : le prix du marché à l'instant du calcul.
- *Pourquoi elle était séduisante* : c'est la lecture naïve de « l'outil doit donner le vrai prix » ;
  aucune donnée à gérer, aucune péremption à expliquer, et l'utilisateur n'a jamais à se demander si
  son chiffre est frais — il l'est toujours.
- *Ce qui l'a disqualifiée* : irreproductible par construction, et une démonstration de soutenance
  serait à la merci d'un timeout provoqué par notre propre mock.
- *Ce qui nous y ferait revenir* : si les prix devenaient contractuels, horodatés et archivés **par
  le fournisseur**, l'archive pourrait vivre chez lui plutôt que chez nous.

**Option C — cache mémoire**
- *Ce qu'elle proposait* : garder les prix quelques minutes dans le processus.
- *Pourquoi elle était séduisante* : dix lignes de code, elle absorbe les pannes courtes et supprime
  la plupart des appels réseau — le gain immédiat le plus élevé pour l'effort le plus faible.
- *Ce qui l'a disqualifiée* : un cache n'est pas une archive. Il ne survit pas au redémarrage, n'a
  pas d'identifiant citable dans un résultat, et ne peut pas être montré à quelqu'un qui demande
  « d'où sort ce chiffre ».
- *Ce qui nous y ferait revenir* : **en complément**, devant la lecture des snapshots, si le nombre
  de lectures devenait un problème. Jamais à la place.

**Hypothèses de travail**
- **24 h** comme seuil de péremption : valeur métier jamais fournie (ambiguïté A6 du cadrage), donc
  paramétrable et affichée. *Risque* : si le métier attend une semaine, tous nos snapshots
  apparaîtront périmés à tort, et le marqueur perdra son sens à force d'être allumé.
- La prise de snapshot est **explicite** (action utilisateur ou commande), pas automatique à chaque
  calcul. *Risque* : un utilisateur peut travailler longtemps sans en reprendre ; c'est précisément
  ce que l'affichage de l'âge doit rendre visible.
- Les trois devises du catalogue sont des prix **indépendants**, pas des conversions : aucun taux de
  change n'est lu à l'exécution.

## Conséquences

**Positives**
- Reproductibilité démontrable : deux calculs sur le même identifiant de snapshot donnent le même
  total au centime.
- Le repli en cas de panne est le comportement normal, pas un cas d'erreur : on utilise le dernier
  snapshot valide.
- L'âge et le statut sont des données, donc affichables en permanence et testables.

**Négatives**
- Il faut une politique de prise de snapshot, et l'expliquer à l'utilisateur.
- Le stockage croît avec le nombre de prises (≈ nombre de pièces achetées × nombre de prises).
- Un utilisateur peut décider en connaissance de cause sur des prix périmés — l'outil le signale,
  il ne l'empêche pas.

**Dette acceptée**
- Aucune purge des anciens snapshots, aucune comparaison entre deux snapshots. À revoir si le volume
  devient gênant ou si la question « qu'est-ce qui a changé depuis lundi ? » est activée.

## Comment on saura qu'on s'est trompé

Deux calculs référençant le même snapshot donnent des totaux différents (la promesse est rompue), ou
l'observation que l'utilisateur travaille en permanence en `STALE` sans jamais reprendre de snapshot
— signe que la prise ne doit pas être manuelle.
