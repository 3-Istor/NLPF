# Glossaire du domaine — 3istor

- **Date** : 2026-09-22
- **Lecteur visé** : un coéquipier qui rejoint le projet dans six mois.
- **Règle** : un terme de ce glossaire a exactement ce sens dans le code, dans l'API et à l'écran.
  Les identifiants anglais entre parenthèses sont ceux employés dans le code.

---

## 1. Les quatre notions que tout le monde confond

C'est la section à lire en premier. Sur un arbre, ces quatre mots se confondent sans dommage. Sur un
graphe, les confondre produit des totaux faux.

### Exemple de référence (le « losange »)

```
            V (véhicule)
           /             \
      × 2 /               \ × 3
        A                   B
      × 4 \               / × 5
           \             /
                 S (vis)
```

| Notion | Sur cet exemple | Valeur |
|---|---|---|
| **Pièce** | `S` est **une** pièce, une seule ligne en base, un seul prix | 1 pièce |
| **Occurrence** | `S` est montée à deux endroits : `V→A→S` et `V→B→S` | 2 occurrences |
| **Quantité unitaire** | Portée par l'arête `A→S` : il faut 4 vis pour **un** `A` | 4 |
| **Quantité cumulée** | Ce qu'il faut de `S` pour **un** véhicule : `2×4 + 3×5` | **23** |

Une implémentation qui répond « 1 » à la dernière ligne traite le graphe comme un arbre. Une qui
répond « 9 » a oublié de multiplier par la quantité du parent. Les deux erreurs sont silencieuses :
seul un jeu de valeurs de contrôle les révèle.

---

## 2. Structure de la nomenclature

| Terme | Définition |
|---|---|
| **Nomenclature**, **BOM** (*Bill of Materials*) | La description complète de ce qui compose le véhicule : des pièces, et les liens « X est composé de N fois Y ». |
| **Graphe orienté acyclique**, **DAG** | Structure de la BOM : des nœuds reliés par des liens orientés, sans jamais pouvoir revenir sur ses pas. **Ce n'est pas un arbre** : un nœud peut avoir plusieurs parents. |
| **Pièce** (`part`) | Un article identifié par une **référence** unique. Existe en un seul exemplaire en base, quel que soit le nombre d'endroits où elle est montée. |
| **Référence** (`part_ref`) | L'identifiant stable et lisible d'une pièce (ex. `FIX-M6-16`). Ce que l'utilisateur cherche et cite. |
| **Arête** (`edge`) | Le lien « le parent P est composé de *q* unités de l'enfant C ». Porte la **quantité unitaire** et son unité. Une paire (parent, enfant) est **unique**. |
| **Racine** (`root`) | L'unique pièce sans parent : le véhicule complet. |
| **Feuille** (`leaf`) | Une pièce sans enfant. Par construction, toute pièce **achetée** est une feuille (voir §4). |
| **Orphelin** | Une pièce déclarée mais employée nulle part. Interdit : la validation du jeu de données refuse le fichier. |
| **Occurrence** | **Un emplacement de montage** d'une pièce, identifié par son **chemin** depuis la racine. Une pièce a autant d'occurrences que de chemins qui mènent à elle. |
| **Chemin** (`path`) | La suite d'arêtes de la racine jusqu'à une occurrence, ex. `V→A→S`. **C'est l'identité d'une ligne de l'arbre à l'écran**, pas la référence. |
| **Pièce partagée** | Une pièce ayant **plusieurs parents**. Elle apparaît à plusieurs endroits de l'arbre et porte le badge « utilisée à N endroits ». Ce n'est pas un doublon de données. |
| **Where-used** | La liste de tous les chemins d'utilisation d'une pièce. Répond à « où est montée cette vis ? ». |
| **Profondeur** | Le nombre de niveaux sous la racine. |
| **Système** | Un grand ensemble fonctionnel du véhicule (motopropulseur, transmission, châssis, carrosserie, intérieur, électricité, fluides, visserie, matières). Sert à la décomposition affichée dans la synthèse. |
| **Tri topologique** | Ordre de parcours garantissant qu'un nœud est traité après tous ses enfants (ou avant tous ses parents, selon le sens). Sert à la fois à **prouver l'acyclicité** et à ordonner le calcul. |

---

## 3. Quantités

| Terme | Définition |
|---|---|
| **Quantité unitaire** (`edge_quantity`) | Ce que porte **une arête** : combien d'enfants pour **un** parent. Locale : elle ne dit rien du véhicule complet. |
| **Quantité cumulée** (`cumulative_quantity`) | Ce qu'il faut de cette pièce pour **un véhicule complet**. Formellement : la somme, sur **tous** les chemins de la racine à la pièce, du **produit** des quantités unitaires du chemin. |
| **Valeur de contrôle** | La quantité cumulée attendue, stockée dans le jeu de données et vérifiée par les tests du moteur. Quelques-unes sont vérifiables à la main (le pneumatique à 5, roue de secours comprise). |
| **Unité** (`unit`) | `pce`, `kg`, `m`, `L`… Un nombre sans unité n'est pas une information : l'unité est affichée partout. |

---

## 4. Valorisation et coût

| Terme | Définition |
|---|---|
| **Mode de valorisation** (`valuation_mode`) | Comment une pièce obtient son coût. Exclusif : `purchased` **ou** `manufactured`, jamais les deux (ADR-0008). |
| **`purchased`** (achetée) | Le coût est le **prix d'achat**. La pièce est une **feuille** : aucun enfant. On ne somme jamais d'enfants dessus. |
| **`manufactured`** (fabriquée) | Le coût est la **somme des enfants plus la main-d'œuvre**. La pièce **n'a pas** de prix propre. On ne cherche jamais son prix dans le snapshot. |
| **Coût unitaire** (`unit_cost`) | Ce que coûte **une** unité de la pièce, dans la devise du calcul. Achetée : prix × multiplicateur fournisseur × coefficient d'usine. Fabriquée : somme des enfants + main-d'œuvre. |
| **Contribution** (`contribution`) | Ce que cette pièce apporte **au total du véhicule** : quantité × coût unitaire. La somme des contributions égale toujours le total. |
| **Vue agrégée** | Une ligne par **pièce**, avec sa quantité cumulée et sa contribution totale. Répond à « quelles pièces pèsent le plus ? ». |
| **Vue par occurrence** | Une ligne par **chemin**. Répond à « combien coûte cette vis *à cet endroit-là* ? ». |
| **Main-d'œuvre** (`labour`) | Temps d'assemblage d'un ensemble fabriqué, en minutes, converti en coût par le **taux horaire**. |
| **Taux horaire** (`labour_rate`) | Coût d'une heure de main-d'œuvre. Donnée globale du scénario, pas une règle. |
| **Règle de coût** (`cost_rule`) | Un modificateur **activable et nommé**, enregistré dans un registre (ADR-0006). Une seule en v1 : `labour`. La liste des règles actives est enregistrée avec le calcul. |
| **Double comptabilisation** | L'erreur que la structure interdit : compter le prix d'un ensemble **et** celui de ses composants. |

---

## 5. Prix, fournisseurs et provenance

| Terme | Définition |
|---|---|
| **Catalogue de prix** | Le prix de référence de chaque pièce achetée, en EUR, USD et RUB, avec ses min/max sur l'année. Alimente la mock API. |
| **Fournisseur** (`supplier`) | Qui vend la pièce. Porte un **multiplicateur de prix** et un **délai**. |
| **Site**, **usine** (`plant`) | D'où la pièce sort physiquement. Un fournisseur déclare plusieurs sites. Chaque site porte une **origine**, un **coefficient de prix** et un **CO₂ de transport** (ADR-0010). |
| **Origine**, **provenance** (`origin`) | Le pays du site retenu. **Levier indépendant du fournisseur** : même fournisseur, usine différente, prix et CO₂ différents. |
| **Prix unitaire** | `prix de référence × multiplicateur fournisseur × coefficient d'usine`. Décomposable ligne à ligne dans l'explication. |
| **Prix forcé** (`price_override`) | Valeur imposée manuellement par l'utilisateur sur une pièce, **avec justification textuelle obligatoire**, horodatée et stockée avec le scénario. |
| **Snapshot de prix** (`price_snapshot`) | Une photographie datée et **immuable** des prix, stockée en base et citée par son identifiant dans chaque calcul (ADR-0003). |
| **Âge du snapshot** | Temps écoulé depuis sa prise. Affiché en permanence. |
| **`FRESH` / `STALE`** | Snapshot de moins de 24 h / de plus de 24 h. Un snapshot périmé n'empêche pas le calcul : il le **marque**. |
| **`DEGRADED`** | Résultat obtenu par **repli** sur un snapshot antérieur, l'API n'ayant pas répondu. Visible sur le total **et** sur les lignes concernées. |
| **`INCOMPLETE`** | Résultat auquel il manque au moins un prix, sans historique pour y suppléer. Les pièces concernées sont listées nommément. **Jamais** remplacées par zéro. |
| **Quarantaine** | Mise à l'écart d'une valeur aberrante renvoyée par l'API : elle n'entre pas dans le snapshot. Journalisée avec la valeur rejetée, le motif et la valeur retenue à la place. |
| **Repli** (`fallback`) | Utilisation de la dernière valeur saine connue à la place d'une valeur indisponible ou rejetée. Toujours signalé. |

---

## 6. Scénario et calcul

| Terme | Définition |
|---|---|
| **Scénario** (`scenario`) | L'ensemble des paramètres saisis par l'utilisateur : fournisseurs, sites, devises, prix forcés, temps de main-d'œuvre, règles actives. Persisté et rechargeable. |
| **Paramètre** (`parameter`, `override`) | Un réglage posé sur une pièce. Porte toujours une **portée**. |
| **Portée** (`scope`) | Ce que le réglage affecte : `part` (toutes les occurrences de la pièce) ou `path` (cette occurrence-là uniquement). Affichée à l'écran, jamais implicite (ADR-0002). |
| **Calcul** (`calculation`) | L'exécution du moteur sur un scénario et un snapshot. Persisté avec ses versions (BOM, snapshot, règles), son horodatage et sa devise. |
| **Devise d'achat** | Celle dans laquelle une pièce est payée. |
| **Devise d'affichage** | Celle dans laquelle le résultat est présenté. |
| **Snapshot de calcul** (`CalculationSnapshot`) | Un calcul **nommé et figé** avec les hypothèses qui l'ont produit (copie des paramètres, taux horaire, devise, règles actives), et des références vers le calcul, le snapshot de prix et la version de BOM validée. Immuable, sauf son nom (ADR-0014). À ne pas confondre avec le **snapshot de prix** (§5), qui photographie les prix et est partagé par tous les calculs. |
| **Reproductibilité** | Mêmes entrées + même snapshot ⇒ même résultat, **au centime**. |
| **Explicabilité** | Pouvoir descendre du total jusqu'au prix unitaire d'une pièce et à sa source. |
| **État du calcul** | `à jour` · `paramètres modifiés depuis le dernier calcul` (totaux **obsolètes**) · `calcul en cours` · `échec`. Donnée renvoyée par l'API, pas une décoration du front. |
| **Programmation dynamique** | Chaque pièce n'est évaluée **qu'une seule fois**, son résultat étant réutilisé par tous ses parents. C'est ce qui distingue le moteur d'une récursion naïve, et c'est vérifié par un compteur d'appels. |
| **Mémoïsation** | Le fait de retenir le résultat déjà calculé d'une pièce. Sa **clé** dépend de la portée des paramètres (ADR-0002). |

---

## 7. Mots que nous n'employons pas

| À éviter | Pourquoi | À dire à la place |
|---|---|---|
| « arbre » pour la BOM | C'est un graphe ; le mot induit l'erreur de conception que le projet veut éviter | « le graphe », « le DAG », « l'arborescence » pour la seule vue écran |
| « quantité » tout court | Ambigu entre unitaire et cumulée — l'ambiguïté la plus coûteuse du projet | « quantité unitaire » ou « quantité cumulée » |
| « composant » | Synonyme flottant de pièce, de sous-ensemble et d'occurrence | « pièce », « ensemble » ou « occurrence » |
| « doublon » | Une pièce partagée qui apparaît deux fois n'est pas un doublon | « occurrence » |
| « prix » d'un ensemble fabriqué | Un ensemble fabriqué n'a pas de prix, il a un coût calculé | « coût unitaire » |
| « cache » pour le snapshot | Un cache se perd ; un snapshot s'archive et se cite | « snapshot » |
