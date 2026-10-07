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

## Lancer avec Docker

Depuis la racine du dépôt, Docker démarré :

```bash
docker-compose up
```

Ouvrir **http://localhost:5173** lorsque les services sont prêts. Le premier
lancement construit les images, initialise PostgreSQL, charge la nomenclature
synthétique validée et prend le premier snapshot de prix. Cliquer sur
**Calculer** pour obtenir le coût.

Seuls Docker et Compose **2.20.3 ou supérieur** sont nécessaires : aucune
installation locale de Python ou Node, ni création de `.env`.
`docker compose up` fonctionne également. Les services écoutent sur les ports
5173 (écran), 8000 (API), 8099 (simulateur) et 5432 (PostgreSQL).

`Ctrl+C` arrête les services. Les données restent dans le volume `db-data` :
les relancements ne rechargent pas la nomenclature et ne créent pas de snapshot
supplémentaire. `docker-compose down` conserve également ce volume.
**`docker-compose down -v` détruit les données.**

Pour consulter un échec : `docker-compose logs backend db mock-api`.
Une nomenclature non validée ou un premier snapshot impossible bloque le
backend avec un diagnostic, sans effacer les données existantes.

Après une modification du code, reconstruire avec `docker-compose up --build`.
Si le port 5432 est déjà occupé par une autre application, lancer
`POSTGRES_PORT=55432 docker-compose up` ; seuls les accès PostgreSQL depuis
l'hôte changent, les services continuent à communiquer sur le réseau Docker.
Les ports peuvent être personnalisés avec `FRONTEND_PORT`, `BACKEND_PORT`,
`PRICE_API_PORT` et `POSTGRES_PORT` dans l'environnement du terminal.

---

## Développement sans conteneurs applicatifs

Les étapes suivantes sont l'alternative pour lancer Python et Node localement.
Pour lancer uniquement PostgreSQL, utiliser `docker compose up -d db` depuis
`car-cost/`.

### Prérequis

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

## Lancer l'application manuellement

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
docker compose up -d db
```

Le schéma est appliqué au premier démarrage : les migrations sont montées dans
`docker-entrypoint-initdb.d`. Pour repartir de zéro :

```bash
docker compose down -v && docker compose up -d db
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

## Démonstration : import d'une variante de carrosserie

Une variante de carrosserie se crée en important un modèle 3D (`.glb`, glTF 2.0
binaire) : l'application mesure le volume de chaque pièce, en déduit sa masse
(volume × densité de la matière), compare à la nomenclature, puis crée une
**variante** de la version d'origine et la chiffre sur le snapshot de prix de
l'origine. La maquette du véhicule est servie par l'API et s'affiche dans
l'onglet 3D. Décision : [ADR-0017](car-cost/docs/adr/0017-import-de-variante-de-carrosserie-3d.md).

> **Ce que le chiffre est, et n'est pas.** L'écart affiché est un **impact
> matière** (masse et prix de la matière, plus les fixations ajoutées), **pas un
> coût complet** : l'outillage, le temps de fabrication et le reste de la
> chaîne ne sont pas rechiffrés. Les densités, la maquette et les prix sont
> **synthétiques** : aucun ne vient d'un constructeur.

Fichiers de démonstration, dans `car-cost/seeds/demo/` :

| Fichier | Contenu | Résultat attendu |
|---|---|---|
| `capot-alu.glb` | le capot passe de l'acier à l'aluminium, même géométrie | −1,33 € et −7,35 kg |
| `aileron.glb` | un aileron `BODY-SPOILER` en ABS, 4 vis `FIX-M8-20` | +6,52 €, et la vis M8 passe de 204 à **208** |
| `carrosserie-alu.glb` | capot, pavillon, quatre portes et hayon en aluminium | −8,33 € et −45,92 kg de matière |
| `capot-surface.glb` | le capot est une surface ouverte | refus `MESH_NOT_CLOSED`, qui nomme le capot |

La maquette de référence (`car-cost/seeds/body_multipla.glb`) se régénère avec
`python -m tools.body_model` ; `--check` vérifie qu'elle est inchangée.

Déroulé en trois minutes, sur la nomenclature Multipla :

1. ouvrir le Multipla, puis l'onglet 3D ; cliquer sur le capot : l'arbre suit ;
2. importer `capot-alu.glb` : le capot est coloré, −1,33 €, −7,35 kg ;
3. importer `aileron.glb` : l'aileron apparaît, +6,52 €, la vis M8 passe à 208 ;
4. réimporter la maquette : « aucun changement », l'écran revient à l'origine ;
5. importer `capot-surface.glb` : refus `MESH_NOT_CLOSED`, qui nomme l'objet ;
6. importer `carrosserie-alu.glb` : cinq pièces colorées, −8,33 € et −45,92 kg.

Chaque fichier est un véhicule complet : il est **toujours comparé à
l'origine**, même importé depuis une variante. Importer `carrosserie-alu.glb`
depuis la variante « aileron » donne une variante sans aileron, comme la 3D.
Importer deux fois le même fichier redonne la même variante (« déjà importé »),
que l'écran rouvre. Le sélecteur **Modèle**, au-dessus des onglets, passe de
l'origine à une variante importée (libellée du nom de son fichier) : arbre,
synthèse, écart et 3D suivent.

**Fiche pièce.** Un clic sur une pièce, dans la 3D ou dans l'arbre, ouvre sa
fiche : référence, libellé, matière, masse, quantité cumulée, coût unitaire et
contribution, et, sur une variante, l'avant et l'après. Sur la variante
« aileron », un clic sur l'aileron ouvre `BODY-SPOILER` sous `CAR-ASSY` : 3,15 kg
de `MAT-ABS-GRANULE`, 4 × `FIX-M8-20`, 6,52 €. Sur « carrosserie-alu », un clic
sur une porte avant ouvre `CAR-DOOR-SHELL-FRONT` : acier → aluminium,
9,40 → 3,23 kg, 24,60 → 23,48 €.

Les valeurs ci-dessus sont celles du snapshot figé aux **prix de référence**.
En démonstration, les prix figés à l'instant donnent d'autres valeurs, avec la
même mécanique. L'import est refusé (409 `INCOMPLETE_CALCULATION`) si une pièce
n'a pas de prix dans le snapshot ; le CO₂ n'est pas affiché pour une variante
(il n'est pas recalculé).

### Base existante : à recréer

La migration 0008 ajoute les densités et le stockage des variantes, mais **ne
remplit pas** les versions de nomenclature déjà validées (elles sont
immuables). Sur une base créée avant cette mise à jour, l'import répond
`MATERIAL_WITHOUT_DENSITY` ou `MODEL_NOT_FOUND`. Il faut la recréer :

```bash
docker compose down -v && docker compose up -d
```

**Cette commande efface les données locales : scénarios, snapshots de prix et
snapshots de calcul sont perdus.** Prendre un nouveau snapshot de prix ensuite
(l'écran le propose, et le premier lancement en prend un).

---

## Les tests

```bash
# backend — 772 tests
cd car-cost && source backend/.venv/bin/activate && python -m pytest backend

# front — 187 tests
cd car-cost/frontend && npm test
```

Les soixante-six tests d'intégration se **sautent** si Postgres n'est pas
joignable : la suite reste verte hors ligne. Mesuré sous WSL (Python 3.12) :
`706 passed, 66 skipped` hors ligne, `772 passed` avec la base chargée et
migrée jusqu'à 0008 (le démarrage de l'API rattrape les migrations
manquantes). Les tests d'intégration qui écrivent le font dans une
transaction annulée : un
snapshot ne se supprime pas, et un snapshot de test deviendrait celui que
l'écran utilise. Les tests d'import de variante créent des variantes
(immuables) et les retirent en fin de module en désactivant les déclencheurs
de gel (rôle superutilisateur requis) : les lancer sur une base jetable.

Deux contrôles valent d'être lancés à la main :

```bash
# le schéma refuse-t-il vraiment ce qu'il prétend refuser ?
docker compose exec -T db psql -U 3istor -d 3istor -q \
  < backend/migrations/checks/contraintes.sql
# attendu : 32 refus, 0 WARNING

# le générateur est-il déterministe ?
python -m tools.bom_generator --check
python -m tools.body_model --check   # idem pour la maquette 3D
```

---

## Où lire quoi

| Chemin | Contenu |
|---|---|
| [AGENTS.md](AGENTS.md) | Comment contribuer, seul ou avec un assistant : les règles qu'on ne discute pas, ce que la CI refuse, comment pousser |
| [docs/cadrage.md](car-cost/docs/cadrage.md) | Le problème, les acteurs, 5 questions métier, 5 invariants, 3 modes de panne, 11 ambiguïtés |
| [docs/perimetre.md](car-cost/docs/perimetre.md) | Ce qu'on fait, ce qu'on ne fait pas, ce qu'on reporte, la tranche verticale |
| [docs/domain-glossary.md](car-cost/docs/domain-glossary.md) | Pièce, occurrence, quantité unitaire, quantité cumulée — les quatre mots qu'on confond |
| [docs/adr/](car-cost/docs/adr) | Dix-sept décisions d'architecture, avec les options écartées et ce qui nous y ferait revenir |
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
- Empreinte carbone calculée par le même moteur, sur le même parcours que le coût : facteur matière
  ou procédé par pièce, transport ajouté pour une pièce achetée depuis l'usine retenue pour son
  prix, surcharges de chemin comprises. Sans prix, sans masse ou à prix forcé (aucune usine retenue),
  le CO2 d'une pièce est inconnu, jamais zéro, et la pièce est nommée (`parts_without_co2`).
  Décomposée par système et par quinze principaux contributeurs, comme le coût ; alimente
  `co2_delta_kg` de la comparaison, qui reste `null` tant qu'un des deux CO2 est incomplet
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
- Contrôle d'intégrité de la nomenclature dans le domaine
  (`domain/bom_validation.py`) : cycle, orphelin, racine sous un parent, arête
  en double, quantité non positive, valorisation. Le chargeur passe par lui et
  nomme toutes les fautes d'un coup
- Plusieurs nomenclatures : `GET /bom/versions`, version validée figée en base
  (ADR-0013), gardée en mémoire par l'API — un dépliage ne relit plus la base
- `GET /calculations/{id}/explain` (facteurs du prix, vérifiés contre le prix
  enregistré ; enfants et main-d'œuvre d'un ensemble) et
  `GET /calculations/{id}/issues` (lignes au prix malsain, avec un chemin).
  Côté API seulement : l'écran ne les appelle pas encore
- Écran : arbre dépliable, synthèse permanente, panneau de saisie contextuel,
  marquage des modifications, totaux obsolètes signalés
- Recherche dans l'arbre, sans accents ni casse : le compteur parle en
  occurrences (« 1 / 3 résultats (2 pièces) »), Entrée et F3 passent au
  résultat suivant, Maj+Entrée et Maj+F3 reviennent ; aller à un résultat
  déplie ses ancêtres, le sélectionne et le centre ; les correspondances sont
  surlignées sans jamais injecter de HTML. Au plus 50 chemins parcourables par
  pièce, le compteur le dit quand il y en a plus
- **Lot 1a — l'arbre garde son état.** Dépliage, sélection et défilement
  survivent à un recalcul et au F5 ; recalculer ne replie plus rien
- **Lot 1b — un arbre-tableau lisible.** Colonnes alignées, en-tête collant,
  navigation au clavier (↓ ↑ → ← Entrée), indicateur « mise à jour… » pendant
  le rafraîchissement
- **Lot 1c — une recherche sans accents.** Compteur, Suivant et Précédent,
  surlignage, au plus 50 chemins par pièce (`max_paths`)
- **Lot 1d — le snapshot de calcul nommé** (ADR-0014). Figer un calcul sous un
  nom, lister et ouvrir les snapshots, comparer deux snapshots entre eux sans
  recalcul ; un scénario qui porte un snapshot ne se supprime pas. Un snapshot
  ouvert est en lecture seule (réglages de sa copie, marques ●/○ de sa copie,
  synthèse « figé ») ; « Repartir de ce snapshot » crée un scénario éditable
  avec exactement sa copie (`derived_from`), dont le gel produit un nouveau
  snapshot aux prix du jour
- **Empreinte carbone à l'écran.** La synthèse affiche `total_co2` sous le
  coût ; une somme partielle s'intitule « Empreinte carbone partielle » et dit
  combien de pièces n'ont pas de CO₂ connu ; un calcul antérieur au CO₂
  n'affiche ni total ni zéro. « Répartir par Coût / CO₂ » bascule la
  décomposition par système et les principaux contributeurs. L'écart CO₂ des
  comparaisons est arrondi à l'affichage et dit « inconnu » quand l'un des
  deux CO₂ est incomplet. Vérifié à l'écran contre la vraie nomenclature,
  avec et sans prix forcé

- **Quatre nomenclatures au choix** (ADR-0015) : le Multipla et trois Aston
  Martin Valhalla (hybride, thermique et électrique hypothétiques), importées
  des fichiers de la PR #6 par `tools/valhalla_import` au format du Multipla.
  Masse, carbone, main-d'œuvre, usines, délais et fournisseurs alternatifs y
  sont **générés** (synthétiques, déterministes, vérifiés en CI). Sélecteur
  de véhicule dans le bandeau ; un snapshot de prix appartient à sa
  nomenclature. Migration 0006 vérifiée sur une base existante.
  Comme sur le Multipla, une pièce qui ne diffère que par son emplacement
  (gauche/droite, avant/arrière, conducteur/passager) est une pièce et une
  quantité, et les fixations sont regroupées par type et partagées entre
  ensembles. Un détail **synthétique** porte chaque Valhalla à environ mille
  pièces sur six niveaux : composants des pièces chères, matières et
  visserie standard partagées, sous-ensembles par zone. Le coût de
  référence est conservé au centime.
- **SAV** : un scénario peut compter les pièces de rechange livrées avec le
  véhicule ; l'arbre affiche « + n SAV » à côté de la quantité montée.
- **Prix qui varient** : l'API simulée rejoue une année de marché en 40 min.
  Mode **direct** (calcul aux prix de l'instant, jamais enregistré, rafraîchi
  toutes les 5 s) ou **snapshot** ; « Figer les prix maintenant » depuis
  l'écran.
- **Page Fournisseurs** : par véhicule, chaque fournisseur, ses usines et ses
  pièces ; un clic sur une pièce affiche la courbe de son prix sur l'année
  simulée et ses prix figés. Vérifié dans le navigateur sur une pile isolée.

### Ce qu'il reste à faire

**Import de variante de carrosserie (3D)**

- [ ] **Les trois Valhalla** (recentrage §5, V1 à V6) : ni maquette, ni densités ;
      un véhicule sans modèle répond `MODEL_NOT_FOUND` et l'écran le dit. Le
      sandwich carbone n'a pas de densité : la règle métier est à trancher
      avant de le mesurer.
- [ ] **Commentaires par pièce** : non commencés.
- [ ] **Les quatre matières sans densité** (`MAT-ADHESIVE-PU`, `MAT-BITUMEN-PAD`,
      `MAT-FOAM-PU`, `MAT-GLASS-FIBER`) et les matières au m², au L ou au g :
      une pièce faite de l'une d'elles est refusée à l'import
      (`MATERIAL_WITHOUT_DENSITY`).
- [ ] **Pas un coût complet** : l'écart d'une variante est un impact matière
      (matière et fixations ajoutées) ; main-d'oeuvre, outillage et CO₂ ne sont
      pas rechiffrés.
- [ ] **Pilotage navigateur non fait par les agents** : rendu WebGL, couleurs,
      clic 3D vers l'arbre et la fiche, message sans modèle sur une Valhalla.
      Liste de contrôle dans le rapport de recette (`T13-report.md`).
- [ ] **Constats mineurs ouverts**, sans effet sur les chiffres :
      l'erreur de chargement d'une fiche pièce est avalée par `Workspace.tsx` ;
      la fiche affiche « — » pour les coûts avant/après quand aucun calcul n'est
      ouvert, alors que `body-changes` les sert ; un clic 3D n'amène pas la ligne
      de l'arbre à l'écran, et reste muet si la pièce n'a pas de « où utilisé » ;
      le moteur 3D peut fuir un renderer sur exception et ne libère pas les
      textures ; le verrou d'import ne protège qu'un seul processus (plusieurs
      workers uvicorn, ou deux imports simultanés, peuvent créer deux scénarios) ;
      la SAV n'est pas reportée sur l'arête d'une nouvelle matière ; `EUR` est
      codé en dur dans les réponses d'import ; un cumul à plus de six décimales
      serait arrondi à l'écriture.

**Suite du lot 1 et lots suivants (vues)**

- [ ] **Lot 1-bis** : panneau de saisie pré-rempli et suppression d'un réglage,
      types générés depuis l'OpenAPI, `test:e2e`. (Le sélecteur de version
      de BOM est fait.)
- [ ] **Valider l'ADR-0015** (plusieurs nomenclatures, prix en direct jamais
      enregistrés), rédigé au statut « proposé », et fermer la PR #6 qu'il
      remplace.
- [ ] **Relire les fourchettes générées pour la Valhalla**
      (`tools/valhalla_import/enrich.py`, `suppliers.py`, `detail.py`) :
      décompositions, prix des matières et des standards, zones, masse, carbone,
      heures d'assemblage et usines sont des ordres de grandeur, à discuter.
      Environ un quart des pièces gardent le profil de prix « défaut ».
      Les prix de motorisation du thermique (×1,34) et de l'électrique
      (×2,86) sont recalés pour tenir leur coût à −5 % / +5 % de l'hybride ;
      l'électrique y gagne des moteurs à ~33 k€ pièce et un pack à ~27 k€,
      à confronter à un ordre de grandeur réel.
      Fixations : une pièce par type, au prix du fournisseur majoritaire
      (Würth). Les interfaces que le fichier achetait chez Tier-1 sont
      valorisées au prix Würth par défaut ; Tier-1 reste une offre, à son
      prix le plus fréquent (sur l'électrique, les vis HV à 2,34 € y sont
      comptées à 1,76 €).
- [ ] **Placer les snapshots sur la courbe de prix.** Ils sont datés en temps
      réel, la courbe en temps simulé : ils sont listés à côté. Il faudrait
      enregistrer la date simulée (`as_of` de l'API) avec chaque snapshot.
- [ ] **Lot 2.3 — décomposition de l'écart.** Deux snapshots de calcul pris sur
      des snapshots de prix différents ne se comparent pas aujourd'hui (422) ;
      les comparer, c'est décomposer l'écart entre prix et hypothèses.
- [ ] **Lot 3 — export et import de snapshots de calcul.** « Repartir de ce
      snapshot » et `derived_from` existent depuis le lot 1 ; le refus d'un
      réglage copié qui ne s'applique plus n'est exercé que sur des doubles
      de test tant qu'aucun snapshot n'est importé.
- [ ] **Renommer un snapshot depuis l'écran.** `PATCH /calculation-snapshots/{id}`
      existe ; aucun contrôle ne l'appelle.
- [ ] **Route groupée `children:batch`** pour rafraîchir l'arbre en une requête
      (voir la dette sur la durée du rafraîchissement).
- [ ] **Décision d'équipe sur l'emplacement des ports** (D8) : les nouveaux
      ports vivent dans `application/ports.py` en attendant.

**Tranche T2 — « l'outil dit la vérité sur ses prix »**

- [ ] **Lister les prix de repli à l'écran.** La route existe
      (`GET /calculations/{id}/issues`) ; la synthèse ne l'appelle pas encore.
- [ ] **Expliquer un montant à l'écran.** `GET /calculations/{id}/explain`
      existe ; aucun panneau ne l'affiche.
- [ ] **CO₂ dans l'arbre.** `rolled_up_co2` est au contrat de dépliage
      (docs/api.md §2) mais n'est pas servi : le CO2 unitaire complet n'est
      pas enregistré par ligne. Demande une colonne, donc une migration.
- [ ] **Statut carbone distinct.** Le statut du calcul ne parle que des prix :
      un prix forcé donne `OK` avec un CO2 incomplet. `parts_without_co2` le
      dit ; un `co2_status` le rendrait lisible d'un coup d'œil.
- [ ] **CO₂ dans `/explain` et dans la recommandation de sourcing**, qui ne
      raisonnent encore qu'en euros.
- [ ] **Devises USD et RUB.** Le catalogue les porte, l'application ne sert que
      l'euro. Le réglage `purchase_currency` d'un paramètre est accepté et
      persisté mais **n'a aucun effet** sur le prix (docs/api.md §3.3).
- [ ] **Vue par occurrence** — une ligne par chemin, bornée à un sous-arbre.

**Tranche T3 — « l'outil aide à décider »**

- [ ] **Valider l'ADR-0012** (comparaison sur snapshot commun, recommandation
      pièce par pièce), rédigé en revue au statut « proposé ».

**Dette assumée, nommée**

- **L'arbre-tableau manque de place à 1 280 px.** Les colonnes fixes et la
  synthèse (380 px) laissent au libellé une centaine de pixels : les libellés
  sont tronqués et la colonne « état » rogne ses pastilles (« utilisée à N
  endroits »). Les références longues sont coupées proprement, avec le texte
  entier au survol. À trancher : resserrer les colonnes, raccourcir la pastille,
  ou laisser l'arbre défiler horizontalement.
- **Un test de la recherche a échoué une fois sur dix lancements** (« F3 passe
  au suivant et boucle »), sans se reproduire ensuite. Cause non trouvée.
- **Le rafraîchissement après recalcul est plus lent que le seuil.** Mesuré à
  395–448 ms pour 12 nœuds dépliés, au-dessus des 300 ms visés par l'ADR-0009 :
  l'arbre relit chaque nœud ouvert, un par un. Un indicateur « mise à jour… »
  l'annonce ; la route groupée `children:batch` est différée.
- **L'URL ne garde pas le snapshot ouvert** : un F5 rouvre le scénario vivant
  du snapshot, pas le snapshot.
- **Deux snapshots de calcul sur des snapshots de prix différents ne se
  comparent pas** (ADR-0012, ADR-0014) : l'API refuse (422), l'écran le dit.
- **Le pliage des accents diverge entre Python et TS.** `casefold` côté API,
  `toLowerCase` côté écran : `ß` donne `ss` d'un côté et reste `ß` de l'autre.
  Sans effet hors surlignage.
- **Un calcul orphelin peut rester** si deux gels simultanés visent le même
  nom : le second est refusé (409) mais son calcul a déjà été écrit.
- **La base doit porter les migrations 0003 à 0005** (snapshots de calcul et
  scénarios qui en repartent). Le démarrage de l'API les rattrape ; une base qui
  n'a jamais démarré avec cette version n'a que 0001 et 0002.
- **Le coefficient d'usine n'est pas versionné.** `supplier_plant` est hors du
  périmètre figé par l'ADR-0013 : le modifier change l'explication d'un calcul
  ancien. `/explain` le détecte (`reproduced: false`) sans pouvoir retrouver
  l'ancienne valeur.
- **Un snapshot relu oublie ses pièces sans prix.** Elles n'ont pas de ligne en
  base, seulement un compte. Relu, un snapshot où une pièce n'avait aucun prix
  s'affiche `fresh` ; le calcul, lui, reste `INCOMPLETE` et nomme la pièce —
  rien n'est silencieux, mais la pastille du snapshot ment. Corriger demande de
  stocker ces références (migration).
- **La date d'un prix de repli est fausse.** `as_of` vaut la date du snapshot
  qui reprend le prix, pas celle du prix. Sur une chaîne de replis, seul
  `fallback_from_snapshot_id`, remonté de proche en proche, dit d'où vient la
  valeur. En attendant, `/explain` renvoie `as_of: null` sur ces lignes plutôt
  qu'une date fausse ; les lignes déjà écrites sont immuables.
- **Le journal de quarantaine n'est pas protégé en écriture.** Snapshot et
  lignes de prix ont leur déclencheur d'immutabilité ; `price_quarantine` non.
  L'ajouter fait passer le contrôle du schéma de 26 à 27 refus.
- **Le motif de quarantaine est une phrase**, pas le code prévu par le contrat
  initial (docs/api.md §5.3). Suffisant pour l'écran ; pas pour trier.
- **Comparer et recommander enregistrent de nouveaux calculs** à chaque appel,
  même quand un calcul de même empreinte existe déjà sur ce snapshot : la table
  `calculation` grossit plus vite que nécessaire.
- **Pas de purge des snapshots**, pas de recalcul incrémental. Chacune a son
  signal de réouverture dans
  [docs/perimetre.md](car-cost/docs/perimetre.md) §3.

**Reporté, avec sa condition de déclenchement**

L'optimiseur de combinaison fournisseurs, l'analyse de sensibilité multi-pièces,
l'export, le versionnement de la nomenclature. Voir `docs/perimetre.md` §3 :
chacun porte le signal observable qui rouvrirait le débat.
