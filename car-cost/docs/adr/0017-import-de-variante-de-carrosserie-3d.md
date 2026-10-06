# ADR-0017 — Importer une variante de carrosserie depuis un modèle 3D (glTF binaire)

- **Date** : 2026-10-06
- **Statut** : proposé
- **Décideurs** : équipe 3istor — cadrage de [recentrage-import-3d.md](../recentrage-import-3d.md)
  §0 et §4, et réponses de l'utilisateur du 2026-10-06 (R1 à R5, reprises ci-dessous)
- **Écarte** : [ADR-0012](0012-comparaison-et-recommandation-par-piece.md) (comparaison entre deux
  versions de nomenclature) et [ADR-0015](0015-plusieurs-nomenclatures-et-prix-en-direct.md)
  (snapshot de prix d'une version). Les deux ADR restent tels quels ; l'écart est dit ici.
- **S'appuie sur** : ADR-0004 (couches), ADR-0011 (décimal exact), ADR-0013 (version validée
  immuable)

## Contexte et problème

Le Multipla doit porter une maquette 3D. Un **ingénieur carrosserie** modifie ou ajoute des pièces
dans son outil de CAO, exporte un fichier, et l'outil en tire une **variante** de la nomenclature,
chiffrée, que l'on compare à l'origine.

**Personas.**

- **Ingénieur carrosserie** : importe le fichier. Il part du modèle du véhicule, que l'outil lui
  fait télécharger, et il sait nommer une matière et une pièce.
- **Ingénieur coût, ingénieur achats, ingénieur projet** : lisent. Ils ouvrent la variante, voient
  la vue 3D liée à l'arbre, les pièces modifiées et l'écart de coût et de masse. Ils n'importent
  rien.

Il faut décider : le format du fichier, la façon de mesurer une masse, la table des densités, ce que
devient une version importée, quel prix la chiffre, et comment on compare deux versions. Plusieurs
de ces décisions sortent du cadre posé par les ADR 0012, 0013 et 0015.

Toutes les valeurs de cet ADR sont des **données synthétiques** : densités, maquette et prix ne
viennent d'aucun constructeur.

## Options envisagées

**Format.** *JT* (ISO 14306) est le format de visualisation de l'industrie, mais il n'a pas de
lecteur web libre ni de lecteur en bibliothèque standard. *glTF 2.0 binaire* (`.glb`) est ouvert,
exportable depuis les outils courants, lisible par `three` côté navigateur, et se lit avec `struct`
et `json`. *OBJ ou STL* : pas de nœuds nommés, pas de propriétés personnalisées.

**Visionneuse.** `<model-viewer>` s'installe vite mais ne donne pas la main sur la sélection par
objet ni sur la coloration d'un ensemble. `three` la donne, au prix d'une dépendance.

**Prix d'une variante.** (a) Un snapshot propre à chaque variante : impossible, un import n'invente
aucun prix. (b) Recopier les prix dans la variante : duplique des données qui changent. (c) Chiffrer
sur le snapshot de l'origine de la filiation : une seule source de prix.

## Décision

### 1. glTF 2.0 binaire (`.glb`) plutôt que JT

On retient le **glTF 2.0 binaire**. Le JT reste le format de l'industrie ; le glTF en tient le rôle
pour le web, faute de lecteur JT libre. Le `.glb` se lit en bibliothèque standard (`struct`, `json`,
`fractions`, `hashlib`), sans dépendance Python ajoutée. L'envoi est un **corps brut**, sans
`python-multipart`. Un fichier dont `extensionsRequired` est non vide (Draco, meshopt) est refusé.

### 2. Format du fichier

- Unités : **mètres**.
- Une pièce est **un nœud** dont `extras.carcost` vaut
  `{"ref": "<REF>", "parts": {"<REF-FIXATION>": "<quantité décimale>"}}`. `ref` est obligatoire ;
  `parts` est facultatif.
- Le **nom du matériau glTF** est la référence de la matière (`MAT-ALU-SHEET`).
- Un nœud sans `extras.carcost` est du **décor** : ignoré.
- Plusieurs nœuds de même `ref` sont les **emplacements de montage** d'une même pièce. Ils
  partagent le **même maillage** (sinon `OCCURRENCES_DIFFER`). La masse est celle d'**une** pièce ;
  le nombre de nœuds est la quantité.

### 3. Masse mesurée

Le volume du solide fermé est Σ p₁·(p₂×p₃)/6 dans le repère monde, calculé **exactement** en
`fractions.Fraction` à partir des float32 (un `float` Python perdrait des chiffres sur le triple
produit, et « réimporter la maquette ne change rien » deviendrait faux). « Fermé » : chaque arête,
identifiée par ses deux positions, est partagée par **exactement deux** triangles. Un volume ≤ 0 est
refusé.

Masse = `arrondi₁₀⁻⁶(volume × densité)`, en `ROUND_HALF_UP` : l'arrondi du projet (ADR-0011,
`price_resolution.to_scale`), pas une règle nouvelle.

**Masse de référence (R1).** La masse mesurée remplace la **quantité de l'arête pièce → matière**,
et non `mass_kg`. « Aucun changement » signifie : même matière et même quantité à 10⁻⁶ près, pour
chaque pièce du modèle. Pour `mass_kg` :

- pièce existante modifiée : `mass_kg := mass_kg − ancienne quantité + masse mesurée` ;
- pièce nouvelle : `mass_kg := masse mesurée`.

Exemple, `INT-DOOR-PANEL-FRONT` : `mass_kg` 2,07 kg, dont 1,6 kg d'ABS. Si l'on mesure 1,5 kg d'ABS,
`mass_kg` devient 2,07 − 1,6 + 1,5 = 1,97 kg ; si l'on mesure 1,6 kg, rien ne change. Même raisonnement
pour `INT-DOOR-PANEL-REAR` (1,652 kg ; 1,4 kg) et `ELE-HARNESS-DOOR` (0,486 kg ; 0,4 kg de cuivre).
La différence entre `mass_kg` et la quantité de matière est la masse du reste de la pièce (fixations
et autres), que l'import ne touche pas.

### 4. Densités (R5)

Colonne `part.density_kg_m3` (migration 0008), `Part.density_kg_m3: Decimal | None` et
`Part.material_ref` au domaine. Données **synthétiques**, à valider. Aluminium : **2 700**, valeur
ronde facile à recalculer à la main (les nuances réelles vont d'environ 2 660 à 2 800).

Les **26 matières au kg** du Multipla :

| Origine | Matière | kg/m³ |
|---|---|---|
| fixée par le cadrage | MAT-STEEL-SHEET | 7 850 |
| fixée | MAT-STAINLESS-SHEET | 7 700 |
| fixée | MAT-ALU-SHEET | 2 700 |
| fixée | MAT-ABS-GRANULE | 1 050 |
| fixée | MAT-PP-GRANULE | 900 |
| fixée | MAT-PC-GRANULE | 1 200 |
| fixée | MAT-GLASS-FLOAT | 2 500 |
| fixée | MAT-EPDM-RUBBER | 1 200 |
| proposée (valeur usuelle) | MAT-ALU-CAST | 2 700 |
| proposée | MAT-BRASS-BAR | 8 500 |
| proposée | MAT-CAST-IRON | 7 200 |
| proposée | MAT-CERAMIC-ALO | 3 950 |
| proposée | MAT-COPPER-WIRE | 8 960 |
| proposée | MAT-HDPE-GRANULE | 950 |
| proposée | MAT-LEAD-INGOT | 11 340 |
| proposée | MAT-NBR-RUBBER | 1 000 |
| proposée | MAT-PA66-GRANULE | 1 140 |
| proposée | MAT-SOLDER-SAC | 7 400 |
| proposée | MAT-STEEL-BAR | 7 850 |
| proposée | MAT-STEEL-SPRING | 7 850 |
| proposée | MAT-WELD-WIRE | 7 850 |
| proposée | MAT-ZINC-COATING | 7 140 |
| **vide** (pas de valeur usuelle unique) | MAT-ADHESIVE-PU | — |
| **vide** | MAT-BITUMEN-PAD | — |
| **vide** | MAT-FOAM-PU | — |
| **vide** | MAT-GLASS-FIBER | — |

Les matières au m², au L ou au g sont **vides par construction** : `MAT-PAINT-BASE` (au litre)
répond `MATERIAL_WITHOUT_DENSITY`. Une matière à densité vide fait de même.

### 5. Maquette générée

`tools/body_model` est **déterministe**, avec `--check` en CI comme les autres générateurs. La
maquette compte **26 pièces, 51 objets** (une pièce montée deux fois donne deux objets au même
maillage) et du **décor** (pare-brise, rétroviseurs, optiques : sans `extras.carcost`). Chaque
pièce y est un **pavé** dont la masse mesurée vaut **exactement** la quantité de matière de la
nomenclature (R1). Le fichier `seeds/body_multipla.glb` est chargé dans `bom_model` avec le jeu de
données. Les Valhalla n'en ont pas.

### 6. Variante gelée et `parent_version_id`

Un import qui change quelque chose crée une **version de nomenclature** :

- id `<parente>+<8 premiers hex du SHA-256 du fichier>` ; `parent_version_id` (migration 0008)
  pointe sur la parente ;
- `is_synthetic = true`, `generator_version = "body-import/1"` ;
- **validée et gelée dans la transaction** qui l'écrit (ADR-0013) : plus aucune écriture ensuite ;
- les pièces de la parente et les **offres** (`part_supplier`) sont recopiées ;
- un import ne crée **jamais de pièce achetée** : il n'invente aucun prix ;
- **pièce nouvelle** : sous `CAR-ASSY`, quantité = nombre d'objets, fabriquée, système `CAR`,
  catégorie `body`, 0 min de main-d'œuvre, carbone 0, libellé = nom du nœud ou, à défaut, la
  référence ; une arête vers sa matière (quantité = masse mesurée) et une par fixation de `parts` ;
- **pièce existante** : l'arête vers la matière est remplacée (matière et quantité du modèle).
  Main-d'œuvre, fixations, parents et quantités ne changent pas. `parts` y est donc **ignoré** ;
- **collision de préfixe** (même id, SHA-256 complet différent) : refus.

### 7. Table `bom_model`

Table **à part** : `bom_version_id` en clé, `glb bytea`, `sha256`, `source` (`generated` ou
`imported`), `created_at`. Elle est **immuable**, avec le même déclencheur que les snapshots.
Rattacher un modèle à une version validée ne touche pas aux tables que 0003 gèle.

### 8. Snapshot de prix : écart à ADR-0015

ADR-0015 rattache le chiffrage d'une version à un snapshot de prix propre à cette version. Une
variante n'a pas de prix à elle. On la chiffre donc sur le **dernier snapshot de prix de l'origine
de sa filiation**, que l'on remonte par `parent_version_id`. Cela vaut pour l'import, pour
`body-changes` et pour le calcul d'un scénario de la variante à l'écran. « Figer les prix » sur une
variante prend le snapshot de l'origine.

### 9. Comparaison entre versions : écart à ADR-0012

ADR-0012 refuse de comparer deux versions de nomenclature différentes. Comparer une variante à sa
parente est le but de la feature : `compare_calculations` **ne refuse plus** deux versions
différentes. Il garde le refus de **snapshots différents** et celui des **calculs incomplets**. La
route `POST /scenarios/compare` garde son propre refus (même version). L'écart est calculé **côté
serveur**, jamais dans le navigateur.

### 10. Main-d'œuvre, CO₂ et limite

Une pièce nouvelle coûte **0 min** de main-d'œuvre. Le CO₂ n'est **pas affiché** sur une variante
(carbone 0 sur une pièce nouvelle ferait paraître la variante plus propre qu'elle n'est).

**Limite à dire.** Le chiffre est un **impact matière** : matière, fixations, main-d'œuvre déjà
connue. Ce **n'est pas un coût de fabrication complet** : ni procédés, ni outillage, ni volumes.
L'outillage compte pourtant : l'acier n'est rentable qu'au-delà d'environ 100 000 caisses par an.

### 11. Codes d'erreur

Toutes les fautes sont rendues **en une fois**, en **422**, avec l'objet et la référence. Rien
n'entre en base si une seule faute existe.

| Cas | Code |
|---|---|
| Pas un glTF 2.0 lisible ; aucun objet `carcost` | `INVALID_MODEL_FILE` |
| Draco, meshopt (`extensionsRequired` non vide) | `UNSUPPORTED_EXTENSION` |
| `ref` ou matériau manquant | `MISSING_SPEC` |
| Maillage non fermé (tôle en surface) | `MESH_NOT_CLOSED` |
| Volume ≤ 0 (normales inversées) | `NON_POSITIVE_VOLUME` |
| Matière inconnue | `UNKNOWN_MATERIAL` |
| Matière sans densité (`MAT-PAINT-BASE`, au litre) | `MATERIAL_WITHOUT_DENSITY` |
| Fixation inconnue | `UNKNOWN_PART` |
| Fixation fabriquée | `NOT_PURCHASED` |
| `ref` d'une pièce achetée (`CAR-DOOR-HINGE`) | `REF_IS_PURCHASED` |
| `ref` d'un ensemble sans matière (`CAR-BIW-ASSY`) | `NOT_A_MATERIAL_PIECE` |
| Nœuds de même `ref` à maillages différents | `OCCURRENCES_DIFFER` |
| **À valider** : `ref` hors `^[A-Z0-9-]+$`, quantité de fixation non décimale ou ≤ 0, maillage à plusieurs matériaux | `INVALID_SPEC` |

Import sur une version **sans modèle** (les Valhalla) : **404 `MODEL_NOT_FOUND`**. L'import part du
modèle de la version ouverte ; sans lui, rien n'est mesurable contre rien.

### 12. Réponses de l'import

- **201** : variante créée, avec son écart sur la parente ;
- **200 « aucun changement »** : aucune masse ni matière ne change à 10⁻⁶ près. Pas de variante,
  écart 0, rien n'est écrit ;
- **200 « déjà importé »** (R3) : même fichier sur la même parente. Même variante, **même écart par
  rapport à la parente**, rien n'est créé ;
- **sans snapshot** de prix : la variante est créée, `cost_status = NO_PRICES`, jamais 0 €.

### 13. Lecture (R4)

- `GET /api/v1/bom/{version}/model` : le GLB (`model/gltf-binary`), ou 404 `MODEL_NOT_FOUND` ;
- `GET /api/v1/bom/{version}/body-changes` : la parente, les pièces modifiées ou nouvelles avec leur
  masse avant et après, et l'écart calculé côté serveur sur le snapshot de l'origine. C'est ce que
  la vue 3D lit quand on rouvre une variante.

### 14. Base existante (R2)

La migration 0008 **ne remplit pas** les densités des versions déjà validées (le déclencheur 0003
les gèle, et la donnée est synthétique). On **repart d'une base vide** : le README impose
`docker compose down -v` et signale la perte des scénarios et des snapshots locaux. Aucun agent ne
lance cette commande.

### 15. Vue 3D

**three.js**, lié à l'arbre ; `<model-viewer>` est écarté. `three` est la seule dépendance
d'exécution ajoutée, chargée **à la demande** (`import()`). **À valider** : `@types/three` en
devDependency. Il ne fournit que des types et n'est pas livré au navigateur. Aucune arithmétique
métier dans le navigateur : montants et masses voyagent en chaînes, et seul `src/format.ts`
arrondit.

## Conséquences

- Migration `0008` : `part.density_kg_m3`, `bom_version.parent_version_id`, table `bom_model` et son
  déclencheur. Les migrations `0001` à `0007` ne changent pas.
- Le moteur de coût ne change pas. Le domaine reste en bibliothèque standard ; l'application
  n'importe pas l'infrastructure (ADR-0004). Aucune règle métier en SQL.
- Les écrivains partagés avec les Valhalla n'écrivent `density_kg_m3` que pour un jeu qui déclare
  des densités : les Valhalla restent identiques à l'octet près.
- La variante s'écrit dans **une** transaction ; le scénario et le calcul après. Un échec entre les
  deux laisse une variante sans scénario, que l'écran sait recréer.
- Le `+` de l'id est littéral dans un chemin d'URL mais vaut une espace dans une chaîne de requête
  tapée à la main : le front encode.
- Le chiffre d'une variante change si un nouveau snapshot de l'origine apparaît : c'est voulu, une
  seule source de prix. L'écart est toujours recalculé, jamais lu dans le navigateur.
- Hors périmètre : les Valhalla, les commentaires par pièce, les procédés et l'outillage.
- Ce qui reste à valider par l'utilisateur : la table des densités, `INVALID_SPEC`, le format
  `extras.carcost`, `@types/three`, le refus d'import sans modèle.
