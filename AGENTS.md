# Travailler sur 3istor avec un assistant

Ce fichier est lu par les agents (Claude Code, Codex, Cursor…) au début de
chaque session. Il dit ce qu'il faut savoir pour ne pas casser ce projet sans
s'en apercevoir.

Le lancement, les prérequis et l'état d'avancement sont dans le
[README](README.md). Ici, on parle de **comment contribuer**.

---

## Le projet en trois lignes

Un outil qui calcule le coût de fabrication d'une Fiat Multipla à partir de sa
nomenclature, et l'explique jusqu'au prix unitaire d'une vis. La nomenclature
est un **graphe**, pas un arbre. Les prix viennent d'une API qui tombe.

Python / FastAPI · React / TypeScript · PostgreSQL. Pas de changement de pile
sans ADR.

---

## Cinq faits à connaître avant de toucher au code

1. **La nomenclature est un DAG.** La vis M6 est montée sous le moteur *et* sous
   la caisse. Une pièce a plusieurs parents. Tout raisonnement en arbre est faux
   ici, et faux **silencieusement** : le total reste plausible.
2. **Quatre mots qu'on confond.** Pièce, occurrence, quantité unitaire, quantité
   cumulée. Sur un arbre ils coïncident ; ici non. Lire
   [docs/domain-glossary.md](car-cost/docs/domain-glossary.md) §1 avant d'écrire
   la moindre ligne qui manipule des quantités.
3. **Deux montants par ligne.** `own_contribution` (le coût propre — c'est lui
   qui se somme au total) et `rolled_up_contribution` (ce que pèse une
   occurrence, enfants compris — il ne se somme **pas** entre niveaux). Les
   additionner ensemble, c'est compter deux fois.
4. **Onze ADR** décrivent les décisions structurantes et les options écartées.
   Une décision qui les contredit n'est pas une amélioration, c'est une
   régression — sauf à écrire un nouvel ADR.
5. **Les données sont synthétiques.** Aucun chiffre ne vient d'un constructeur.
   Ne jamais les présenter autrement, ni dans le code, ni à l'écran, ni en
   soutenance.

---

## Les règles qu'on ne discute pas

| Règle | Pourquoi | Ce qui la fait respecter |
|---|---|---|
| Une pièce est `purchased` **xor** `manufactured`. Achetée ⇒ feuille avec prix. Fabriquée ⇒ enfants, sans prix propre. | Rend la double comptabilisation impossible par construction, pas seulement improbable | Clés étrangères composites en base, contrôles à la génération et à l'import, tests |
| Le domaine n'importe ni `fastapi`, ni `sqlalchemy`, ni `psycopg`, ni `urllib`, ni `socket` | Le moteur doit se tester sans base ni réseau, sinon le test-d'abord devient impraticable | `tests/test_layer_dependencies.py`, qui porte aussi son propre garde-fou |
| Aucune règle métier dans une requête SQL | Une règle en SQL n'est testable qu'avec une base et ne peut pas être une stratégie enregistrée | Revue ; les requêtes restent descriptives (filtrer, joindre, compter, paginer) |
| Aucune arithmétique métier dans le navigateur | Deux vérités qui coexistent finissent par diverger | Les montants voyagent en **chaînes** : `a.amount + b.amount` concatène et saute aux yeux |
| L'arrondi est un acte d'affichage, jamais de calcul | Dix montants arrondis ne somment pas au total arrondi ; l'invariant tombe | `src/format.ts` est le seul endroit qui arrondit ; test sur les chaînes sérialisées |
| La route de dépliage n'a **pas** de paramètre de profondeur | Un front qui possède le graphe finira par calculer dessus | Test : passer `depth=99` ne change rien |
| Un prix manquant n'est jamais un zéro | Un zéro se lit comme « cette pièce est gratuite » et minore le total en silence | Le calcul est marqué `INCOMPLETE` et les pièces sont nommées |
| Un snapshot enregistré ne se modifie pas | « D'où sort ce chiffre ? » doit avoir une réponse trois mois plus tard | Déclencheur en base |

---

## Comment travailler ici

**Le test avant le code**, pour toute logique de domaine. Écrire le test, le
voir échouer **pour la bonne raison**, puis le faire passer. Un test qui ne peut
pas échouer ne vérifie rien.

**Une tranche à la fois.** Le découpage est dans
[docs/perimetre.md](car-cost/docs/perimetre.md) §4. On ne commence pas la
suivante avant que la précédente passe ses tests.

**Un ADR avant une décision structurante**, pas après. Écrit après le code, il
devient une justification, et ça se voit. Critères et format dans
[docs/adr/README.md](car-cost/docs/adr/README.md).

**Pas de dépendance sans justification** d'une ligne dans le message de commit.
`pyproject.toml` porte la raison de chacune en commentaire.

**S'arrêter plutôt qu'inventer.** Si une règle métier manque — un taux, un
seuil, un arrondi, une portée — ne pas choisir en silence. Exposer le problème,
proposer une réponse, attendre. Les hypothèses déjà prises sont listées dans
[docs/cadrage.md](car-cost/docs/cadrage.md) §6, chacune avec son risque.

---

## Ce que la CI refusera

`.github/workflows/ci.yml` tourne sur chaque push et chaque PR. Elle échoue si :

- un test échoue, côté backend ou côté front ;
- les types TypeScript ne passent pas ;
- **les tests d'intégration sont sautés** — une suite verte parce qu'elle s'est
  sautée ne prouve rien ;
- une contrainte du schéma ne tient plus, ou le nombre d'écritures interdites
  refusées n'est plus 15 — un contrôle supprimé ne doit pas passer inaperçu ;
- le générateur n'est plus déterministe — sinon rien n'empêche de modifier
  `seeds/` à la main et de faire mentir les valeurs de contrôle du moteur.

Lancer la même chose en local avant de pousser :

```bash
cd car-cost && source backend/.venv/bin/activate
python -m pytest backend
python -m tools.bom_generator --check
cd frontend && npx tsc --noEmit && npm test
```

---

## Conventions

- **Français** pour la documentation, les commentaires et les messages de
  commit. **Anglais** pour le code et les identifiants.
- **Messages de commit à l'impératif**, un commit par comportement. Le corps dit
  *pourquoi*, pas *quoi* — le diff dit déjà quoi.
- Un commentaire explique une **raison**, pas une mécanique. `# on incrémente i`
  n'a pas sa place ; « sans cet arrondi à la source, un total sort avec
  vingt-cinq décimales de bruit » en a une.
- Les fins de ligne sont en LF (`.gitattributes`). Le générateur compare des
  octets : un CRLF casserait son contrôle de déterminisme.

Si votre assistant a produit du code, ajoutez-le en co-auteur — l'historique
doit dire qui a écrit quoi :

```
Co-Authored-By: <Nom du modèle> <noreply@exemple>
```

---

## Pousser

Le dépôt est sur GitHub : `3-Istor/NLPF`. À ce jour, `git push origin main`
fonctionne sans passer par une PR — c'est ainsi que les commits actuels sont
arrivés.

Malgré tout :

- **Une branche et une PR** pour tout ce qui touche au schéma, à un ADR, au jeu
  de données ou à la frontière entre couches. La CI tourne sur les PR, et une
  décision structurante mérite un relecteur humain.
- **Push direct sur `main`** acceptable pour de la documentation, un test
  supplémentaire, une correction évidente — à condition d'avoir lancé la suite
  en local avant.
- **Jamais de `--force` sur `main`.** L'historique de ce projet est un livrable :
  il doit raconter la même histoire que la soutenance.
- Ne jamais commiter `node_modules/`, `.venv/`, ni un fichier de secrets. Le
  `.gitignore` les couvre ; vérifiez quand même ce que vous ajoutez.

---

## Anti-patterns constatés sur ce projet

Chacun s'est réellement produit ici, et a coûté du temps :

- **Traiter le DAG comme un arbre** « parce que c'est plus simple à coder ». Le
  moteur naïf donne les mêmes résultats que le bon sur une fixture jouet.
- **Arrondir à la sérialisation.** L'écart valait deux millionièmes d'euro sur
  474 pièces — invisible à l'écran, faux quand même.
- **Lier le panneau de saisie au dépliage.** Une pièce achetée est une feuille :
  le réglage le plus utile devenait inatteignable.
- **Confondre occurrences et quantité cumulée.** La roue complète est à trois
  endroits, en cinq exemplaires, sous deux parents : trois nombres différents.
- **Partager un venv entre WSL et Windows.** Les deux écrivent dans le même
  `.venv` et se détruisent mutuellement.
- **Écrire un test qui ne peut pas échouer** : une fixture où libellé et
  référence portent le même texte, un helper qui écrase le cas qu'on voulait
  tester.
