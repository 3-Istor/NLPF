# ADR-0016 — Un paramètre de scénario peut porter son propre taux horaire

- **Date** : 2026-10-05
- **Statut** : proposé
- **Décideurs** : équipe 3istor — demande du 2026-10-05 : « je veux que le taux horaire soit dans
  chaque pièce »
- **Révise** : l'hypothèse A4 du [cadrage](../cadrage.md) (« un taux horaire unique »)

## Contexte et problème

Jusqu'ici, le taux horaire était une donnée **globale** du scénario : toutes les minutes de
main-d'œuvre de tous les ensembles étaient payées au même prix. La demande est de pouvoir régler ce
taux **ensemble par ensemble**, depuis le panneau du nœud, comme on y règle déjà le temps.

## Options envisagées

### Option A — Le taux reste global, le panneau ne fait que le recopier
*Apporte* : aucun changement au moteur ni au schéma.
*Coûte* : ne répond pas à la demande : changer le taux sur un ensemble change le coût de tous les
autres.

### Option B — Un taux par atelier ou par pays d'assemblage
*Apporte* : un modèle plus proche de l'industrie.
*Coûte* : une nouvelle dimension (atelier, pays) que la nomenclature ne porte pas, et que personne
n'a demandée.

### Option C — Un champ `labour_rate` sur le paramètre de scénario
Le paramètre porte déjà `labour_minutes`, avec une portée pièce ou chemin (ADR-0002). On y ajoute un
taux, nullable. Sans valeur, c'est le taux du scénario qui s'applique.

## Décision

**Option C.** Le taux du scénario devient le **taux par défaut**. Un paramètre peut le remplacer sur
sa cible.

Le paramètre de chemin reste une **cible complète** (ADR-0002, `Scenario.parameter_for`) : ce qu'il
ne précise pas vient de la nomenclature et du taux du scénario, jamais du paramètre de portée pièce.
Un chemin qui ne règle que le taux paie donc le temps de la nomenclature à ce taux, même si un
paramètre de pièce a changé le temps.

## Conséquences

- Migration `0007` : une colonne `labour_rate` sur `scenario_parameter` et sur sa copie figée
  `calculation_snapshot_parameter`. Un snapshot de calcul dit donc quel taux a servi (ADR-0014).
- Le taux n'a de sens que sur un ensemble fabriqué : sur une pièce achetée, il est refusé comme le
  temps (ADR-0008).
- Les taux posés entrent dans l'empreinte des entrées, ce qui rend obsolète le calcul précédent.
  Ils n'y entrent **que s'il y en a**, pour que les calculs déjà enregistrés gardent leur empreinte.
- Ni `ENGINE_VERSION` ni `RULES_VERSION` ne changent : sans taux posé, chaque résultat reste
  identique au centime près.
- L'écran pré-remplit le champ avec le taux du scénario. Laissé tel quel, il n'est **pas** envoyé :
  la pièce suit alors les changements futurs du taux du scénario.
