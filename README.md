# 3istor — coût de fabrication d'une Fiat Multipla 1.6 16V

Outil d'aide à la décision qui calcule le coût de fabrication d'un véhicule à
partir de sa nomenclature, et l'explique jusqu'au prix unitaire d'une vis.

Il remplace un classeur de 300 Mo que plus personne ne pouvait auditer. La
difficulté n'est pas l'addition : une nomenclature **n'est pas un arbre** — la
même vis M6 est montée sous le moteur *et* sous la caisse — et les prix viennent
d'une API qui tombe.

> **Les données sont plausibles mais synthétiques.** Prix, masses, facteurs
> carbone, coefficients d'usine et délais ont été fabriqués pour être cohérents
> entre eux. Aucun ne provient d'un constructeur. L'application le répète à
> l'écran.

---

## Prérequis

| Outil | Version | Pourquoi |
|---|---|---|
| **Python** | 3.12 ou plus | backend et générateur de nomenclature |
| **Node.js** | 20 ou plus | front (Vite 6) |
| **Docker** | avec Compose v2 | Postgres 16 |
| **git** | — | — |

Vérifier :

```bash
python --version && node --version && docker compose version
```

### Sur Ubuntu

Ubuntu 24.04 fournit Python 3.12 ; sur 22.04, il faut l'ajouter (dépôt
`deadsnakes` ou équivalent).

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git curl
```

**Docker.** Installer le moteur et le greffon Compose depuis le dépôt officiel
Docker — le paquet `docker.io` d'Ubuntu ne fournit pas toujours `docker compose`
en version 2. Puis, pour ne pas préfixer chaque commande par `sudo` :

```bash
sudo usermod -aG docker "$USER"   # puis se déconnecter / reconnecter
docker compose version            # doit afficher v2.x
```

**Node.** Le paquet `nodejs` d'Ubuntu est souvent trop ancien. Passer par nvm :

```bash
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.40.1/install.sh | bash
exec "$SHELL"
nvm install 22 && nvm use 22
```

### Sous Windows

Docker passe par WSL 2. Les commandes `docker compose` se lancent depuis un
terminal WSL, ou depuis Windows si Docker Desktop expose le port.

**Gardez un terminal WSL ouvert.** Lancer `docker compose up -d` par une
invocation WSL ponctuelle (`wsl -e bash -lc "…"`) démarre bien le conteneur,
mais celui-ci s'arrête quelques secondes après la fin de la commande — Postgres
journalise alors `database system was not properly shut down` au redémarrage
suivant. Depuis une session WSL interactive, le problème ne se produit pas.

---

## Lancer l'application

Cinq étapes. Les trois premières ne servent qu'une fois.

**Chaque bloc part de la racine du dépôt** (le dossier qui contient ce
fichier). Les `cd` ne s'enchaînent donc pas d'un bloc à l'autre.

Les commandes sont identiques sur Ubuntu et sous Windows. **Dans chaque terminal
que vous ouvrez**, placez-vous dans `car-cost/` et activez le venv — ensuite,
`python` désigne celui du projet :

```bash
cd car-cost
source backend/.venv/bin/activate        # Ubuntu, macOS, WSL
# source backend/.venv/Scripts/activate  # Windows, Git Bash
# backend\.venv\Scripts\Activate.ps1     # Windows, PowerShell
```

L'invite affiche alors `(.venv)`. À refaire dans chaque nouveau terminal : une
activation ne franchit pas les fenêtres — une variable posée ailleurs non plus.

> **Un venv ne se partage pas entre WSL et Windows.** Les deux écrivent dans le
> même `backend/.venv` mais dans des dossiers différents — `bin/` d'un côté,
> `Scripts/` de l'autre — et le second créé rend le premier inutilisable :
> `No Python at '/usr/bin\python.exe'`. Si vous passez de l'un à l'autre,
> supprimez `.venv` et recréez-le.

### 1. La base

```bash
cd car-cost
docker compose up -d
```

Le schéma est appliqué au premier démarrage : les migrations sont montées dans
`docker-entrypoint-initdb.d`. Pour repartir de zéro :

```bash
docker compose down -v && docker compose up -d
```

### 2. L'environnement Python

```bash
cd car-cost/backend

python3 -m venv .venv                                  # Ubuntu, macOS
# python -m venv .venv                                 # Windows

.venv/bin/python -m pip install -e ".[dev]"            # Ubuntu, macOS
# .venv/Scripts/python.exe -m pip install -e ".[dev]"  # Windows
```

Le projet s'installe en mode **éditable** : `uvicorn` et `pytest` trouvent alors
le paquet sans qu'on ait à manipuler `PYTHONPATH`.

### 3. La nomenclature en base

Le jeu de données est déjà dans `car-cost/seeds/` et versionné. Pour le charger :

```bash
cd car-cost && source backend/.venv/bin/activate
python -m carcost.infrastructure seeds \
  | docker compose exec -T db psql -U 3istor -d 3istor -v ON_ERROR_STOP=1 -q
```

Le chargeur **n'écrit rien** si le jeu de données échoue un contrôle :
acyclicité par tri topologique, racine unique, aucun orphelin, valorisation
exclusive, quantités cumulées recalculées et comparées à celles annoncées.

Pour régénérer les fichiers (le générateur est déterministe, deux exécutions
produisent les mêmes octets) :

```bash
cd car-cost && source backend/.venv/bin/activate
python -m tools.bom_generator            # écrit seeds/ et imprime son rapport
python -m tools.bom_generator --check    # vérifie le déterminisme, n'écrit rien
```

### 4. Les prix

L'API de prix est un **simulateur** qu'on peut faire tomber à la demande.

```bash
# terminal A — le simulateur
cd car-cost && source backend/.venv/bin/activate
python price-api/mock_price_api.py --port 8099

# terminal B — prendre un snapshot
cd car-cost && source backend/.venv/bin/activate
python -m carcost.infrastructure.snapshot_cli
```

Les modes de panne, pour la démonstration :

```bash
CLI="python -m carcost.infrastructure.snapshot_cli"

$CLI --fail timeout --timeout 1  # l'API se tait → le snapshot précédent reste en vigueur
$CLI --fail outlier              # prix négatif → quarantaine, dernier prix sain retenu
$CLI --fail garbage              # valeur illisible → quarantaine
$CLI --fail missing              # pièce absente → repli, ou pièce nommée sans prix
```

### 5. L'API et l'écran

```bash
# terminal C — l'API
cd car-cost && source backend/.venv/bin/activate
python -m uvicorn carcost.infrastructure.api.main:app --port 8000

# terminal D — l'écran (pas de venv ici : c'est du Node)
cd car-cost/frontend
npm install        # une seule fois
npm run dev
```

L'écran est sur **http://localhost:5173**. Le front appelle l'API par un proxy
Vite ; il n'y a pas de CORS à configurer.

---

## Les tests

```bash
# backend — 201 tests
cd car-cost && source backend/.venv/bin/activate && python -m pytest backend

# front — 15 tests
cd car-cost/frontend && npm test
```

Les onze tests d'intégration se **sautent** si Postgres n'est pas joignable : la
suite reste verte hors ligne. Vérifié sous WSL (Python 3.12) : `190 passed,
11 skipped` hors ligne, `201 passed` avec la base chargée. Les tests
d'intégration qui écrivent le font dans une transaction annulée : un snapshot ne
se supprime pas, et un snapshot de test deviendrait celui que l'écran utilise.

Deux contrôles valent d'être lancés à la main :

```bash
# le schéma refuse-t-il vraiment ce qu'il prétend refuser ?
docker compose exec -T db psql -U 3istor -d 3istor -q \
  < backend/migrations/checks/contraintes.sql
# attendu : 15 refus, 0 WARNING

# le générateur est-il déterministe ?
python -m tools.bom_generator --check
```

---

## Où lire quoi

| Chemin | Contenu |
|---|---|
| [AGENTS.md](AGENTS.md) | Comment contribuer, seul ou avec un assistant : les règles qu'on ne discute pas, ce que la CI refuse, comment pousser |
| [docs/cadrage.md](car-cost/docs/cadrage.md) | Le problème, les acteurs, 5 questions métier, 5 invariants, 3 modes de panne, 11 ambiguïtés |
| [docs/perimetre.md](car-cost/docs/perimetre.md) | Ce qu'on fait, ce qu'on ne fait pas, ce qu'on reporte, la tranche verticale |
| [docs/domain-glossary.md](car-cost/docs/domain-glossary.md) | Pièce, occurrence, quantité unitaire, quantité cumulée — les quatre mots qu'on confond |
| [docs/adr/](car-cost/docs/adr) | Onze décisions d'architecture, avec les options écartées et ce qui nous y ferait revenir |
| [docs/api.md](car-cost/docs/api.md) | Les contrats d'API, écrits avant l'implémentation |
| [backend/migrations/](car-cost/backend/migrations) | Le schéma, et ce qu'il garantit ou non |
| [seeds/validation_report.json](car-cost/seeds/validation_report.json) | Le rapport du générateur : 474 pièces, 689 arêtes, 65 partagées |

---

## Où en est le projet

**La tranche T1 est terminée** : on descend de la racine jusqu'à une vis, on
change son fournisseur, les totaux passent en obsolète, on recalcule, et le
nouveau total est explicable jusqu'à la date du snapshot qui l'a fourni.

Le total calculé par l'API sur la nomenclature réelle — **13 285,66 €** — est
celui que le générateur avait calculé de son côté, par un chemin de code
entièrement distinct.

### Fait

- Nomenclature exhaustive : 474 pièces, 689 arêtes, profondeur 5, **65 pièces à
  parents multiples**, générateur déterministe, rapport de validation à zéro erreur
- Moteur de coût par programmation dynamique sur le DAG : une évaluation par pièce dans le cas
  courant, et seulement les préfixes concernés réévalués lorsqu'une surcharge de chemin existe
- Schéma Postgres dont les contraintes rendent la double comptabilisation
  impossible, vérifié sur une vraie base
- Snapshot de prix immuable, repli sur timeout, quarantaine des valeurs
  aberrantes, pièces sans prix nommées
- Prix dégradés visibles : chaque ligne d'arbre dit si son prix est frais, de
  repli, en quarantaine ou manquant ; la synthèse compte les lignes concernées
  et affiche le journal de quarantaine, dont chaque entrée déplie l'arbre
  jusqu'à la pièce. Vérifié à l'écran contre la vraie base, sur des snapshots
  `--fail outlier` et `--fail missing`
- API de dépliage nœud par nœud, where-used, recherche, calcul, scénarios, comparaison et
  recommandation de sourcing
- Écran : arbre dépliable, synthèse permanente, panneau de saisie contextuel,
  marquage des modifications, totaux obsolètes signalés

### Ce qu'il reste à faire

**Tranche T2 — « l'outil dit la vérité sur ses prix »**

- [ ] **Lister les prix de repli.** La synthèse les compte, mais seules les
      valeurs en quarantaine sont cliquables (par le journal). Sur une panne
      qui touche trente pièces, les trouver dans l'arbre reste une chasse. La
      route prévue est `GET /calculations/{id}/issues` (docs/api.md §4.5).
- [ ] **Empreinte carbone.** Le moteur a tout ce qu'il faut — facteurs par
      pièce, CO₂ de transport par usine — mais ne calcule que le coût.
- [ ] **Devises USD et RUB.** Le catalogue les porte, l'application ne sert que
      l'euro.
- [ ] **Prix forcé et temps de main-d'œuvre** éditables à l'écran (l'API les
      accepte déjà, avec justification obligatoire).
- [ ] **Vue par occurrence** — une ligne par chemin, bornée à un sous-arbre.
- [ ] **Recherche à l'écran** : l'API renvoie les chemins, le front ne déplie
      pas encore automatiquement jusqu'au résultat.

**Tranche T3 — « l'outil aide à décider »**

- [ ] **Ajouter le CO₂e aux calculs et aux comparaisons.** Le delta de coût, les
      dix principaux écarts et la recommandation de sourcing sont disponibles ;
      la projection carbone dépend encore de NLPF-46 à NLPF-48.

**Dette assumée, nommée**

- **Recalculer replie l'arbre.** On remonte le composant pour que les lignes
  redemandent les nouveaux chiffres, et on perd sa place. Sur 474 pièces c'est
  pénible ; la correction est de rafraîchir les nœuds ouverts en place.
- **Les trois facteurs du prix ne survivent pas au redémarrage.** Le fournisseur
  et l'usine retenus sont persistés ; la décomposition
  `référence × multiplicateur × coefficient` sera recalculée par une route
  `/explain`, pas stockée en double.
- **Un snapshot relu oublie ses pièces sans prix.** Elles n'ont pas de ligne en
  base, seulement un compte. Relu, un snapshot où une pièce n'avait aucun prix
  s'affiche `fresh` ; le calcul, lui, reste `INCOMPLETE` et nomme la pièce —
  rien n'est silencieux, mais la pastille du snapshot ment. Corriger demande de
  stocker ces références (migration).
- **La date d'un prix de repli est fausse.** `as_of` vaut la date du snapshot
  qui reprend le prix, pas celle du prix. Sur une chaîne de replis, seul
  `fallback_from_snapshot_id`, remonté de proche en proche, dit d'où vient la
  valeur. La route `/explain` devra le faire ; les lignes déjà écrites sont
  immuables.
- **Le journal de quarantaine n'est pas protégé en écriture.** Snapshot et
  lignes de prix ont leur déclencheur d'immutabilité ; `price_quarantine` non.
  L'ajouter fait passer le contrôle du schéma de 15 à 16 refus.
- **Le motif de quarantaine est une phrase**, pas le code prévu par le contrat
  initial (docs/api.md §5.3). Suffisant pour l'écran ; pas pour trier.
- **Déplier jusqu'à une pièce ouvre le panneau de chaque ancêtre** (journal,
  contributeurs, recherche) : l'arbre se remplit de panneaux qu'on n'a pas
  demandés.
- **Pas de purge des snapshots**, pas de recalcul incrémental. Chacune a son
  signal de réouverture dans
  [docs/perimetre.md](car-cost/docs/perimetre.md) §3.

**Reporté, avec sa condition de déclenchement**

L'optimiseur de combinaison fournisseurs, l'analyse de sensibilité multi-pièces,
l'export, le versionnement de la nomenclature. Voir `docs/perimetre.md` §3 :
chacun porte le signal observable qui rouvrirait le débat.
