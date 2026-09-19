# NLPF / 3istor — Besoins de l'outil d'aide à la décision

**Statut :** Version de travail — en attente de validation par l'équipe.

## 1. Contexte et objectif

Le projet 3istor vise à développer un outil d'aide à la décision industrielle permettant d'estimer et d'expliquer le coût de fabrication d'une voiture à partir de sa nomenclature, des quantités de composants et de leurs prix.

L'outil doit également permettre d'étudier les conséquences économiques de variations de prix ou de changements de configuration, ainsi que d'estimer l'empreinte carbone des composants.

L'objectif est de fournir à l'utilisateur des informations fiables et compréhensibles pour comparer plusieurs hypothèses de fabrication et éclairer ses décisions.

## 2. Cinq questions métier

L'outil doit permettre à l'utilisateur de répondre aux cinq questions suivantes :

| N° | Question métier                                                                                                         |
| -- | ----------------------------------------------------------------------------------------------------------------------- |
| 1  | Combien coûte la fabrication de ma voiture ?                                                                            |
| 2  | Quels composants contribuent le plus au coût total de fabrication ?                                                     |
| 3  | Quel serait l'impact d'une variation du prix d'un composant sur le coût total de fabrication ?                          |
| 4  | Quelle est l'empreinte carbone estimée de ma voiture et quels composants y contribuent le plus ?                        |
| 5  | Quelle configuration de ma voiture permet de réduire son coût de fabrication tout en maîtrisant son empreinte carbone ? |

La comparaison des configurations doit tenir compte des composants, de leurs quantités et des hypothèses de calcul retenues.

Le fonctionnement précis de la création, de la modification et de l'enregistrement des configurations sera défini ultérieurement.

## 3. Cinq invariants non négociables proposés

Les invariants suivants définissent les propriétés que l'application doit respecter pour garantir la cohérence et la fiabilité de ses résultats.

### Invariant 1 — Calculabilité du coût total

Le coût total d'une configuration valide doit pouvoir être calculé à partir de prix exploitables.

Lorsqu'un prix actuel est momentanément indisponible, le dernier prix connu peut être réutilisé, à condition de signaler son ancienneté à l'utilisateur.

Si aucun prix exploitable n'est disponible pour un composant nécessaire, le système ne doit pas inventer de valeur ni présenter un coût incomplet comme un coût total fiable.

### Invariant 2 — Reproductibilité des résultats

À configuration, quantités, prix et règles de calcul identiques, le système doit toujours produire le même résultat.

Les données et hypothèses ayant servi à un calcul doivent permettre de le reproduire, même lorsque les prix actuels ont évolué.

### Invariant 3 — Cohérence du calcul

Toute modification d'un composant, de sa quantité ou de son prix doit être correctement répercutée sur le coût total de la configuration concernée.

Le résultat doit prendre en compte l'ensemble des composants nécessaires et les quantités définies dans la nomenclature.

### Invariant 4 — Immuabilité des snapshots

Un snapshot enregistré ne doit jamais être modifié rétroactivement.

Toute évolution des prix ou de la configuration doit pouvoir donner lieu à un nouveau calcul sans altérer les données et les résultats des calculs précédemment enregistrés.

### Invariant 5 — Absence de double comptabilisation

Un même coût ne doit jamais être comptabilisé deux fois dans le coût total de fabrication.

Lorsqu'un ensemble est valorisé directement, les coûts de ses sous-composants déjà inclus dans cette valorisation ne doivent pas être ajoutés une seconde fois.

Le calcul doit tenir compte du mode de valorisation retenu pour chaque ensemble ou composant.

## 4. Trois pannes possibles de l'API de prix

### Panne 1 — API de prix indisponible

**Situation :** l'API ne répond plus ou dépasse le délai de réponse autorisé.

**Réaction attendue :** le système tente de réutiliser les derniers prix connus et exploitables pour poursuivre le calcul.

L'utilisateur est informé de l'indisponibilité momentanée de l'API et de l'utilisation de prix historiques.

Si les données disponibles ne permettent pas de déterminer un coût total complet, le système doit le signaler.

### Panne 2 — Prix d'un composant manquant

**Situation :** l'API fonctionne, mais ne fournit aucun prix pour un composant nécessaire à la fabrication.

**Réaction attendue :** le système recherche le dernier prix connu et exploitable de ce composant.

Si un tel prix existe, il peut être utilisé pour poursuivre le calcul. L'utilisateur est informé de l'indisponibilité du prix actuel et de la date du prix utilisé.

Si aucun prix exploitable n'est disponible, le système ne doit pas remplacer automatiquement la valeur manquante par zéro ni présenter un résultat incomplet comme un coût total fiable.

### Panne 3 — Prix invalide ou incohérent

**Situation :** l'API retourne une donnée inexploitable, par exemple un prix négatif, une valeur non numérique ou une unité incohérente.

**Réaction attendue :** le système rejette la donnée invalide et tente de réutiliser le dernier prix connu exploitable.

L'utilisateur est informé de l'anomalie et de l'utilisation éventuelle d'un prix historique.

En l'absence de données exploitables, le système ne doit pas produire de coût total présenté comme fiable.
