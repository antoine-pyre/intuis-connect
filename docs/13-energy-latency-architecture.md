# Énergie et retard du cloud : analyse et structure cible

Analyse du 17 novembre 2026, à partir de `fix/hourly-scheduler-event-loop`.
Contexte : le cloud Intuis ne confirme une heure de consommation qu'avec un
retard variable, parfois de plusieurs heures, parfois de plusieurs jours selon
la pièce. Toute la chaîne énergie doit être pensée autour de cette latence.

## 0. Correction préalable

`_replace_external_in_transaction` (`recorder_import.py:216-235`) crée la ligne
`StatisticsMeta` au premier passage, puis se contente de **valider** `source`,
`unit_of_measurement` et `has_sum` sur une ligne existante. Aucun `UPDATE` de
métadonnées n'existe dans le paquet.

Conséquence : les séries externes n'héritent **jamais** d'un changement de
métadonnées. Un correctif sur `unit_class`, un renommage de pièce, un
changement de devise ne touchent que les séries créées après coup. Les séries
existantes gardent leurs valeurs d'origine jusqu'à suppression manuelle.

C'est la première chose à corriger : sans cela, aucun correctif de métadonnées
n'a d'effet sur une installation en service.

## 1. Le constat de fond : deux représentations de la même mesure

| | Capteur d'entité | Série externe |
|---|---|---|
| Identifiant | `sensor.<pièce>_energy` | `intuis_connect:energy_<hash>` |
| Écriture | recorder, depuis les états | transaction directe |
| Granularité | journalière | horaire |
| Sémantique | `TOTAL_INCREASING`, maximum du jour logique | somme révisable |
| Passé | non réécrivable sans ancre | réécrivable librement |

Les deux décrivent la même consommation, par deux chemins qui ne se
réconcilient jamais. C'est la source de la plupart des défauts qui suivent, et
c'est ce qui a produit la corruption de cumul observée lors d'une bascule de
version.

Or **la représentation journalière est redondante** : Home Assistant agrège
lui-même une série horaire en jour, semaine et mois. Le tableau de bord Énergie
ne consomme rien d'autre. Maintenir une seconde série journalière n'apporte
aucune vue que l'horaire ne donne pas, et coûte toute la fragilité ci-dessous.

## 2. Les défauts, par gravité

### 2.1 Le cumul est relatif, sans jamais être réancré

C'est le défaut central, et il n'a rien à voir avec la largeur de la fenêtre.

`async_replace_external_history` poursuit les sommes « depuis la ligne qui
précède la période ». L'ancrage est donc **relatif** : chaque heure écrite
s'appuie sur la précédente, et rien ne redérive jamais le niveau absolu du
cumul à partir d'une source sûre. Une heure manquée, une valeur révisée par le
cloud, une fenêtre mal couverte : l'écart entre dans la somme et y reste pour
toujours.

Le flux Node-RED de référence (`TheFab21/Time-Planning-intuis`) ne souffre pas
de ce défaut, alors qu'il utilise une fenêtre horaire comparable — de minuit
local J-1 à maintenant. Ce qui le sauve est ailleurs :

- il maintient `base_kwh`, le cumul arrêté à **la fin du jour J-2** ;
- une fois par jour, il avance cette base de la consommation de J-2 lue à
  l'échelle **`1day`**, c'est-à-dire la valeur consolidée du cloud ;
- chaque heure importée vaut alors `base du jour + cumul depuis minuit local`,
  donc une valeur **absolue**, recalculable à l'identique.

Le rebase est idempotent : une clé `rebase_j2_done_<jour>` persistée en
contexte fichier, posée seulement après un succès.

Autrement dit, la fenêtre de 48 h est parfaitement suffisante **à condition**
qu'une réconciliation quotidienne la rattrape derrière. Le flux a cette
réconciliation ; l'intégration n'en a aucune. C'est la différence à combler,
pas la largeur de la fenêtre.

Deux conséquences secondaires de l'ancrage relatif :

- un réimport d'une plage chevauchante peut décaler toute la suite, puisque le
  point de départ dépend de la ligne qui précède et non d'une référence
  absolue ;
- le total maison hérite du même défaut, alors que le rebase quotidien le
  donnerait directement et sans dépendre des trous horaires.

### 2.2 L'horizon de clôture est de quinze minutes

`closed_hour_end` (`hourly_series.py:27-31`) considère une heure close quinze
minutes après sa fin. Avec un cloud en retard, la quasi-totalité des heures
récentes de la fenêtre sont absentes à chaque passage. Elles seront comblées
plus tard, mais chaque cycle refait le travail pour rien.

Cet horizon devrait être configurable et refléter la latence réelle du
fournisseur.

### 2.3 Une période sans mesure est traitée comme une erreur

`stage_hourly` lève `APIError("No measured hour in the period")` quand le cloud
ne renvoie rien. Pour une pièce dont les données ont plus de 48 h de retard,
c'est le cas **à chaque cycle**. Le résultat passe en `partial` ou `failed`, la
liste d'erreurs se remplit, et `manager.last_error` affiche en permanence une
panne qui n'en est pas une.

« Aucune heure confirmée pour l'instant » est un état normal, pas une erreur.

### 2.4 Le total maison est tout-ou-rien

`sum_hourly` (`hourly_series.py:70-79`) ne somme que les heures confirmées par
**toutes** les pièces. Avec des latences échelonnées par pièce, l'intersection
est chroniquement vide sur les heures récentes : le total maison reste
`partial` en permanence, comme observé.

Deux sorties possibles : renoncer au total maison et laisser le tableau de bord
Énergie sommer les sources, ou maintenir un filigrane propre au total qui
n'avance que sur les heures complètes, sans marquer le reste en échec.

### 2.5 Le capteur journalier se bat contre le modèle de Home Assistant

`IntuisEnergySensor` (`sensor.py:261`) est `TOTAL_INCREASING` et publie le
maximum du jour logique. Trois conséquences :

- une révision à la baisse par le cloud est invisible, le maximum ne redescend
  jamais dans la journée ;
- une révision à la hausse d'un jour clos n'est jamais reflétée, l'état ne
  décrit que le jour courant ;
- à la remise à zéro, HA interprète la baisse comme un redémarrage de compteur
  et poursuit la somme, ce qui rend toute incohérence de source indétectable.

Un compteur qui dépend de données révisables en amont ne peut pas être un
`TOTAL_INCREASING` alimenté par les états.

### 2.6 L'import journalier exige une ancre vivante

`_replace_in_transaction` (`recorder_import.py:155-195`) refuse l'import s'il
n'existe pas de statistique court terme postérieure à la période. La contrainte
est juste — on ne peut pas réécrire le passé d'un `TOTAL_INCREASING` sans
ancre — mais elle n'existe que parce qu'on écrit dans l'identifiant d'une
entité. Les séries externes n'ont pas ce problème, et le code le dit lui-même.

### 2.7 Les coûts ne couvrent que les heures de la passe courante

Dans `async_import_hourly_history`, `hourly_costs` n'est appliqué qu'à
`confirmed[room_id]`, les heures confirmées **pendant ce passage**. Une heure
dont l'énergie était connue mais dont le prix manquait à ce moment ne sera
jamais recalculée automatiquement : il faut appeler `recalculate_cost_history`
à la main.

Le coût devrait suivre son propre filigrane : toute heure ayant une énergie et
pas de coût valide est à (re)calculer.

## 3. Structure cible

### 3.1 Une seule source de vérité

Les séries externes horaires deviennent la seule histoire. Le capteur d'entité
redevient ce qu'il est bien : un **affichage temps réel**.

Deux façons de le faire, et il faut en choisir une **sans jamais les mélanger** :

- le capteur garde `state_class` et le recorder compile son histoire, mais
  **rien** n'écrit jamais dans son `statistic_id` ;
- ou le capteur perd `state_class` et n'a aucune statistique — et alors il ne
  faut écrire aucune série sous son identifiant, sinon Home Assistant signale
  une classe d'état disparue.

C'est exactement l'erreur commise par une version antérieure : retirer la
`state_class` **et** écrire les statistiques long terme sous l'identifiant de
l'entité. L'une ou l'autre, jamais les deux.

La première option est préférable : elle garde l'entité utilisable dans les
cartes natives et les automatisations, sans contrainte sur le passé.

### 3.2 Un rebase quotidien, comme dans le flux Node-RED

Le mécanisme à reprendre tel quel, parce qu'il tourne en production sur cette
API depuis longtemps :

- une passe quotidienne lit l'échelle `1day` pour **J-2**, valeur consolidée ;
- elle en déduit le cumul arrêté à la fin de J-2, par pièce ;
- la passe horaire couvre **J-1 et aujourd'hui**, et chaque heure vaut
  `base de la journée + cumul depuis minuit local`, une valeur absolue ;
- l'avance de la base est protégée par une clé « déjà fait » datée, posée
  seulement en cas de succès.

Le gain est double. Les trous horaires de J-1 et d'aujourd'hui cessent d'être
critiques, puisque le rebase de J-2 les absorbe le lendemain. Et un réimport
devient idempotent, puisque la somme ne dépend plus de la ligne précédente mais
d'une base datée.

Le choix de J-2 plutôt que J-1 est délibéré : il laisse au cloud une journée
pleine pour consolider.

### 3.3 Un horizon de décantation explicite

Une option, par défaut généreuse (24 h), qui dit au bout de combien de temps on
considère qu'une heure absente ne viendra plus. Elle pilote l'avancée de
`confirmed_through` et remplace les quinze minutes en dur.

### 3.4 Métadonnées idempotentes

À chaque écriture, les champs mutables — `name`, `unit_class`, `mean_type`,
`has_mean` — sont mis à jour sur la ligne existante. Les champs immuables
— `source`, `unit_of_measurement`, `has_sum` — restent validés et refusés en cas
d'écart, comme aujourd'hui.

### 3.5 Les coûts pilotés par leur propre filigrane

Le calcul de coût ne dépend plus de la passe d'énergie. Il parcourt les heures
ayant une énergie confirmée et pas de coût valide, applique le prix de l'heure,
et avance son filigrane. Un prix indisponible laisse l'heure ouverte au lieu de
la perdre.

## 4. Contraintes de Home Assistant à respecter

- **Toute écriture de statistiques passe par le fil du recorder.** La
  `RecorderTask` acquittée actuelle est la bonne approche, à conserver.
- **Les statistiques externes doivent porter un identifiant `domaine:xxx`** et
  ne jamais ressembler à un `entity_id`.
- **`unit_class` doit valoir exactement `energy`** pour qu'une série apparaisse
  dans les sélecteurs du tableau de bord Énergie, qui filtrent sur
  `includeUnitClass=["energy"]`.
- **Les clés de `StatisticMetaData` varient selon la version du recorder.**
  Chaque champ doit être conditionné à son propre support, jamais à celui d'un
  autre.
- **Écrire la ligne de métadonnées directement contourne le cache du
  gestionnaire de HA.** C'est délibéré ici pour que le cache n'apprenne pas un
  identifiant qu'un `ROLLBACK` effacerait, mais cela impose de rester cohérent
  avec le schéma à la main.
- **Home Assistant agrège lui-même** une série horaire en jour, semaine et
  mois. Aucune série journalière n'est nécessaire.

## 5. Migration suggérée

1. **Mise à jour des métadonnées existantes.** Sans elle, rien de ce qui suit
   n'atteint une installation en service.
2. **Rebase quotidien à J-2**, en gardant les séries existantes. C'est l'étape
   qui rend le cumul auto-réparateur et qui absorbe la latence du cloud.
3. **Statut honnête** : « aucune heure confirmée » cesse d'être une erreur.
4. **Coûts découplés**, pilotés par leur filigrane.
5. **Retrait de la voie journalière** : plus aucune écriture dans
   l'identifiant des entités, l'import journalier devient un import horaire sur
   une profondeur choisie. C'est l'étape qui supprime l'exigence d'ancre vivante
   et le risque de cumul corrompu.

Les quatre premières sont additives et sans rupture. La cinquième demande une
décision sur le sort de l'historique déjà écrit sous les identifiants
d'entités.
