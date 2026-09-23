# ADR-0004 — Trois couches, dépendances dirigées vers le domaine, vérifiées par un test

- **Date** : 2026-09-22
- **Statut** : accepté
- **Décideurs** : équipe 3istor

## Contexte et problème

Le domaine ne doit connaître ni écran, ni réseau, ni fournisseur de prix : aucun import de `fastapi`,
`sqlalchemy` ou `httpx` dans la couche métier. C'est une exigence explicite du projet, et sa raison
est pratique : le moteur de calcul doit être testable sur une fixture en mémoire, en millisecondes,
sans Postgres — condition nécessaire pour écrire le test **avant** le code.

Reste à choisir la forme concrète du découpage, et le mécanisme qui le fait tenir quand quatre
personnes travaillent en parallèle sous pression de soutenance.

## Critères de décision

1. **Testabilité du domaine sans base ni réseau.** *Décisif.*
2. Coût pour une équipe de 4 sur quelques semaines.
3. Lisibilité pour un arrivant : où va un nouveau fichier ?
4. Compatibilité avec FastAPI et SQLAlchemy sans lutter contre eux.

## Options envisagées

### Option A — Trois couches avec inversion des dépendances
`domain` (entités, moteur, interfaces de ports) ← `application` (cas d'usage, orchestration) ←
`infrastructure` (FastAPI, SQLAlchemy, client HTTP, dépôts). Les flèches d'import ne vont jamais vers
l'extérieur. Un **test d'architecture** échoue si `domain` importe une bibliothèque d'infrastructure.
*Apporte* : moteur testable en mémoire, règle vérifiée mécaniquement.
*Coûte* : un mapping entre entités et modèles ORM, et plus de fichiers.

### Option B — Services appelant directement l'ORM
Le découpage par défaut de FastAPI : des routes, des services, des modèles SQLAlchemy partout.
*Apporte* : le moins de code, aucun mapping, la vitesse initiale maximale.
*Coûte* : le moteur ne se teste plus sans base.

### Option C — Hexagonale complète avec conteneur d'injection
Ports et adaptateurs pour chaque dépendance, câblage par un conteneur.
*Apporte* : substituabilité totale, symétrie.
*Coûte* : un conteneur à apprendre et à configurer, pour deux adaptateurs réels.

## Décision

**Option A.** Raison décisive : c'est le plus petit découpage qui rend le moteur testable sans
Postgres, et le **test d'architecture** remplace la discipline — la règle tient même quand on code
à minuit avant une soutenance.

Deux ports seulement au départ : `BomRepository` (lire le graphe) et `PriceSnapshotProvider` (lire un
snapshot). Le câblage est explicite dans un module `bootstrap`, sans conteneur.

## Hypothèses et options abandonnées

**Option B — services et ORM directs**
- *Ce qu'elle proposait* : pas de couche domaine séparée ; les modèles SQLAlchemy sont le modèle.
- *Pourquoi elle était séduisante* : c'est le chemin par défaut de l'écosystème, celui de toute la
  documentation FastAPI. Elle supprime le mapping entité/ORM — soit, à vue de nez, 200 à 300 lignes
  et une source d'erreurs — et permettrait de livrer la première tranche plus vite.
- *Ce qui l'a disqualifiée* : le moteur deviendrait intestable sans base ; or le test du DAG en
  losange, écrit avant le code, est la garantie centrale du projet. Et l'exigence est explicite.
- *Ce qui nous y ferait revenir* : si le projet se réduisait à du CRUD sans calcul. Ce n'est pas le
  cas.

**Option C — hexagonale complète avec conteneur**
- *Ce qu'elle proposait* : un port par dépendance, un conteneur pour les câbler.
- *Pourquoi elle était séduisante* : c'est la forme aboutie de la même idée ; elle rendrait
  l'ajout d'une seconde source de prix ou d'une base différente presque gratuit, et elle impressionne
  en soutenance.
- *Ce qui l'a disqualifiée* : aucune de ces substitutions n'est prévue. Il y a deux adaptateurs
  réels. Un conteneur d'injection coûterait plus en compréhension à quatre personnes qu'il ne
  rapporterait — c'est l'abstraction « au cas où » que le projet s'interdit.
- *Ce qui nous y ferait revenir* : au **deuxième adaptateur réel d'un même port** — par exemple une
  seconde source de prix à côté de la mock API.

**Hypothèses de travail**
- Un mapping manuel entités ↔ modèles ORM reste tenable à cette taille. *Risque* : si le mapping
  devient plus volumineux que le domaine lui-même, le rapport coût/bénéfice s'inverse.
- Les entités de domaine sont des objets simples et immuables (`dataclass(frozen=True)`), sans
  paresse ni relations chargées à la demande.

## Conséquences

**Positives**
- Le moteur se teste en millisecondes sur des fixtures en mémoire ; le cycle test-d'abord devient
  praticable.
- Le moteur reste une fonction pure `(BOM, scénario, snapshot) → résultat`, ce qui est la condition
  posée pour l'optimiseur reporté (périmètre §3.1).
- La question « où va ce fichier ? » a une réponse mécanique.

**Négatives**
- Duplication entité / modèle ORM, et le mapping à maintenir.
- Plus de fichiers et un chemin d'import plus long pour une modification simple.
- Tentation permanente de faire passer un objet ORM dans le domaine « juste cette fois » — d'où le
  test, qui doit rester activé.

**Dette acceptée**
- Mapping écrit à la main, pas de conteneur d'injection : le câblage vit dans un module explicite.

## Comment on saura qu'on s'est trompé

Le test d'architecture est désactivé, contourné par des imports paresseux, ou le mapping dépasse en
volume le code de domaine qu'il sert.
