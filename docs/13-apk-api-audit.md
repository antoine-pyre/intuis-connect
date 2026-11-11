# Comparaison du client API avec l’APK Intuis

Audit statique du 11 novembre 2026. **Le client n’est pas entièrement validé
contre l’application officielle.** Plusieurs chemins et champs sont confirmés,
mais l’authentification, les mesures et la sérialisation des plannings diffèrent.
Aucun appel au compte Intuis ni aucune commande aux radiateurs n’a été effectué.

## Application analysée et reproductibilité

- APK fourni localement : `intuis.apk`, paquet `com.muller.intuitiv`.
- Version du manifeste : **2.8.0**, code **12080000**.
- SHA-256 : `7e632cffae98736f68f4719121983fc555daf12d52a199cf939e79357e9b749f`.
- JADX **1.5.6**, Java **17.0.21**. Sources dans `intuis_decompiled/sources/`,
  ressources et manifeste dans `intuis_decompiled/resources/`.
- La passe Java signale 90 erreurs de décompilation sur 10 456 classes ;
  la passe ressources réussit. Les méthodes citées ci-dessous sont lisibles,
  mais cet audit ne constitue pas une reconstruction complète de l’application.
- Les bibliothèques natives et les ressources de densité séparées ne sont pas
  nécessaires à cette comparaison des appels Java ; leurs splits n’ont pas été analysés.

Les noms obfusqués ci-dessous valent pour cet APK précis. Pour reproduire :

```sh
sha256sum intuis.apk
jadx --no-res -d intuis_decompiled intuis.apk
jadx --no-src -d intuis_decompiled intuis.apk
```

Le binaire et les sources décompilées sont exclus de Git. Aucun secret extrait
supplémentaire n’est recopié dans ce rapport ni ajouté aux constantes du client.

## Résultats

| Sujet | Preuve dans les sources décompilées | Comparaison avec le client |
|---|---|---|
| Serveur principal | `resources/res/values/strings.xml`, `base_url_prod` ; `defpackage/gvd.java` | `https://app.muller-intuitiv.net` confirmé. Le serveur de secours du client n’est pas confirmé par cet APK. |
| OAuth | `defpackage/d88.java`, `oh8.java`, `bw7.java` | `/oauth2/token`, formulaires password/refresh, préfixe `muller` et scopes read/write confirmés. Identité et version d’application différentes. |
| Données des maisons | `defpackage/ba5.java`, `fvd.java` | Chemin `homesdata` confirmé. L’app envoie du JSON avec `sync_measurements`, `app_type` et `app_version` ; le client utilise un GET sans ces paramètres. Acceptation du GET non prouvée par cet APK. |
| Statut et configuration | `defpackage/ba5.java`, `fvd.java`, `fi6.java::i0` | Chemins `/syncapi/v1/homestatus` et `/syncapi/v1/getconfigs`, champ `home_id` confirmés. L’app utilise JSON, le client des formulaires. |
| Commande de pièce | `defpackage/ba5.java::setHomeStatus`, `me7.java` | JSON `home.rooms`, champs `therm_setpoint_mode`, température et fin de dérogation compatibles avec le modèle de l’app. Les modes `away` et `boost` envoyés comme modes de pièce ne sont pas confirmés. |
| Changement de planning | `defpackage/t8b.java::e`, `f1b.java::f` | POST JSON `/api/switchhomeschedule`, `home_id`, `schedule_id` confirmés. `schedule_type` est optionnel côté app. |
| Synchronisation de planning | `defpackage/t8b.java::d`, `f1b.java::h`, `fpe.java`, `gma.java` | Même route `/api/synchomeschedule`, mais différences de noms de champs et de structure des pièces, détaillées ci-dessous. |
| Lecture/édition/suppression de créneau héritées | `defpackage/t8b.java` et recherche des chaînes dans toutes les sources | Aucune occurrence de `gethomeschedule`, `updatenewhomeschedule` ou `deletenewhomeschedule`. Ces méthodes du client n’ont pas d’appelant dans le code produit du dépôt et restent non validées. L’app expose `deletehomeschedule` pour supprimer un planning entier, opération différente. |
| Mesures d’énergie | `defpackage/sj7.java::getRoomMeasures`, `rj7.java::j`, `vj7.java`, `rd5.java` | Le flux de l’app utilise POST JSON `/api/gethomemeasure`, y compris pour les pièces. Le client utilise POST formulaire `/api/getroommeasure` et un autre schéma de réponse. |
| Types et addition de l’énergie | `defpackage/yi7.java::g`, `tx1.java::r` | Les six types demandés par le client sont présents. L’app ajoute les types de prix puis les exclut de l’addition énergétique. L’addition des colonnes numériques d’énergie est cohérente avec ce code ; l’unité physique et la complétude des données demandent une réponse réelle. |

## OAuth : différences et limites

`bw7.A()` retourne un client ID se terminant par **e355**, contre **e353** dans
l’intégration. Le secret associé diffère également. `bw7.H()` retourne
`12080000`, contre `1108100` dans le client. La documentation historique qui
présente e355 uniquement comme un client « Node-RED » est donc incomplète : il
est aussi embarqué dans cet APK officiel.

`oh8.a()` envoie `app_version` lors du renouvellement du token. Ce champ manquait
dans le client : il a été ajouté, en gardant la version déclarée par l’intégration.

L’identité OAuth existante est conservée : remplacer les constantes ne migre
pas les refresh tokens déjà émis pour un autre client. La présence d’une identité
dans un APK ne permet pas de déduire ses autorisations actuelles côté serveur,
ni d’affirmer qu’un niveau « webapp » explique à lui seul les écarts d’énergie.

## Plannings : contrat différent à vérifier sur le cloud

La méthode `f1b.h()` construit notamment :

```json
{
  "home_id": "home",
  "schedule_id": "schedule",
  "schedule_type": "therm",
  "name": "Semaine",
  "timetable": [{"zone_id": 1, "m_offset": 0}],
  "zones": [{
    "id": 1,
    "rooms": [{"id": "room", "therm_setpoint_temperature": 20}]
  }]
}
```

`fpe` sérialise `rooms`, `gma` sérialise les pièces et leurs attributs ; les
attributs thermiques figurent dans `me7`. La fonction de synchronisation du client
envoie au contraire `id`, `type` et `rooms_temp: [{room_id, temp}]`.

Les anciens documents du dépôt présentent ce second format comme requis par
des essais antérieurs. L’APK ne permet pas de trancher si le serveur accepte
les deux variantes. Ce schéma n’a donc pas été remplacé sans preuve d’une
incompatibilité réelle. Les tests locaux existants de services simulent le client
API et ne constituent pas une validation de ce contrat serveur.

L’énumération des modes de pièce `kqb` contient `manual`, `home`, `hg`, `off` et
`unknown`. Le mode `away` apparaît au niveau maison dans `t4d`/`le7`. Cela signale
une différence de portée possible pour les presets actuels ; l’absence de `boost`
dans cette énumération ne prouve pas à elle seule son rejet par le serveur.

## Énergie : existence d’une route et utilisation réelle

`vj7.getRoomMeasureUrl()` expose bien `/api/getroommeasure`. Toutefois, les deux
méthodes `sj7.getRoomMeasures()` et `getHomeMeasures()` appellent `rj7.j()` ;
cette dernière utilise `getHomeMeasureUrl()`, donc `/api/gethomemeasure`.
La simple présence de `getroommeasure` parmi les chaînes de l’APK ne valide pas
le chemin pris par le client.

Dans ce flux, la requête contient `home: {id, rooms, modules}`, `scale` et les
dates sous forme de chaînes. `rd5` décrit ce conteneur ; `opa` et `at7` décrivent
les éléments de pièce/module. `HomeMeasureResponseMapper` décrit une réponse
hiérarchique différente des blocs `body: [{beg_time, value}]` du client actuel.
La compatibilité du chemin historique, les périodes sans données et les unités
doivent être vérifiées avec des réponses réelles avant tout remplacement.

## Corrections effectuées et validation locale

Les quatre méthodes de planning héritées construisaient leurs URLs avec
`ENERGY_BASE`, fixé au premier serveur. Après connexion au serveur de secours,
elles pouvaient envoyer le token au mauvais cluster. Elles utilisent maintenant
des chemins relatifs au serveur authentifié ; les paramètres GET/DELETE sont
confiés à aiohttp pour l’encodage. Les routes et payloads existants sont conservés.
Le changement de planning accepte explicitement un identifiant texte ou entier.

Les commandes de pièce et de changement de planning vérifient maintenant aussi
le champ `error` de la réponse JSON, comme l’enveloppe applicative de l’app
(`at4`/`xb0`). Un HTTP 200 contenant un refus n’est plus traité comme un succès.
La réponse de `setstate` est désormais lue et libérée via son context manager.

Treize régressions de transport dans `tests/unit/test_api_contract.py` vérifient les
quatre méthodes sur les deux clusters et le champ de version au refresh, avec
des réponses HTTP simulées, ainsi que les succès/refus applicatifs des deux
commandes. Elles ne prouvent pas que le serveur accepte les
routes héritées. Les tests API existants vérifient aussi les erreurs de transport,
le renouvellement sur 401 et le traitement des valeurs d’énergie.

Commandes de validation :

```sh
python -m pytest tests/unit/test_api_contract.py tests/unit/test_api_energy.py -q
python -m ruff check .
```

Résultat : **198 tests passent** sur les fichiers `test_api_contract`,
`test_api_energy`, `test_overrides`, `test_heating_reconciliation`, `test_climate`
et `test_multi_home_services`, avec Python 3.14.4. Ruff et `git diff --check`
passent également. Le plugin `pytest-socket` 0.7.0, absent de l’environnement
partagé, a été installé dans `/tmp/intuis-audit-test-deps` et ajouté au
`PYTHONPATH`. Les tests de stockage ont nécessité une exécution hors sandbox,
en conservant les sockets réseau externes interdites par pytest. La matrice
complète des deux versions HA n’a pas été rejouée pour cet audit.

## Vérifications encore nécessaires pour valider le client complet

1. Comparer des lectures réelles de maisons/statuts/configuration et d’énergie
   pour le même domicile et la même période, avec les deux formats pertinents.
2. Vérifier la synchronisation sur un planning de test et relire sa définition
   après modification ; comparer les deux schémas sans supposer leur équivalence.
3. Observer les presets de l’app et la portée maison/pièce, puis relire les états
   obtenus et les échéances des dérogations.

Ces points restent ouverts ; aucun succès sur le cloud ou sur du matériel réel
n’est déduit des tests hors ligne.
