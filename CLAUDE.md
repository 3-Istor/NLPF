# CLAUDE.md

**Lis [AGENTS.md](AGENTS.md) en premier.** Tout ce qui compte y est : les cinq
faits à connaître avant de toucher au code, les règles qu'on ne discute pas, la
façon de travailler, ce que la CI refuse, et comment pousser.

Ce fichier ne contient que ce qui est propre à Claude Code.

---

## Au démarrage d'une session

Le projet vit dans `car-cost/`, pas à la racine. Les chemins des documents en
sont relatifs.

Avant de proposer quoi que ce soit sur le calcul, les quantités ou les prix,
lire :

- [car-cost/docs/domain-glossary.md](car-cost/docs/domain-glossary.md) §1 — les
  quatre notions qu'on confond sur un graphe ;
- l'ADR qui couvre la zone touchée ; la table est dans
  [car-cost/docs/adr/README.md](car-cost/docs/adr/README.md).

Ne pas relire tout le dépôt « pour se faire une idée » : les ADR et le glossaire
disent en cinq minutes ce que le code dirait en une heure.

## L'environnement

Python et Node sont installés ; le venv est dans `car-cost/backend/.venv`.
**Il a été créé depuis WSL** : sous Windows, `.venv/Scripts/python.exe` ne
fonctionne plus. Lancer les commandes Python depuis WSL, ou recréer le venv.
S'il manque (clone neuf), le créer avant toute commande :
`cd car-cost/backend && python3 -m venv .venv && .venv/bin/python -m pip install -e ".[dev]"`.

Postgres tourne dans Docker via WSL. Un conteneur démarré par une invocation
ponctuelle (`wsl -e bash -lc "docker compose up -d"`) s'arrête quelques secondes
après la fin de la commande. Deux conséquences :

- enchaîner `up -d`, l'attente et le travail **dans un seul appel** ;
- ne pas s'acharner si le conteneur retombe : dire que la vérification n'a pas
  pu être faite plutôt que d'affirmer un résultat qu'on n'a pas vu.

## Commandes utiles

```bash
# tout depuis la racine du dépôt
cd car-cost && source backend/.venv/bin/activate

python -m pytest backend                 # 774 tests, dont 66 d'intégration Postgres
python -m tools.bom_generator --check    # déterminisme du jeu de données
python -m tools.valhalla_import --check  # idem pour les trois Valhalla
python -m carcost.infrastructure seeds   # émet le SQL de chargement, n'écrit rien
```

Front :

```bash
cd car-cost/frontend && npx tsc --noEmit && npm test
```

## Ce qui est attendu de toi ici

- **Vérifier, pas supposer.** Ce projet a pris l'habitude de faire tourner ce
  qu'il affirme : la migration sur un vrai Postgres, l'API contre la vraie
  nomenclature, l'écran piloté dans un navigateur. Quand une vérification n'a
  pas pu être faite, le dire explicitement.
- **Dire ce qui manque.** Un travail à moitié fait qu'on présente comme terminé
  coûte plus cher que le travail restant. Le README porte une liste « ce qu'il
  reste à faire » ; la tenir à jour fait partie du travail.
- **S'arrêter devant une règle métier absente** au lieu de l'inventer. Exposer
  le problème, proposer une réponse, attendre.
- **Ne pas lancer de serveur en arrière-plan sans le dire**, et le mentionner
  dans la réponse pour que l'humain puisse l'arrêter.

## Attribution

Les commits produits avec Claude portent :

```
Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
```
