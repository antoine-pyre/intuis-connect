# Tests et contrats de régression

La suite protège les points d’entrée réels de l’intégration, avec transport cloud
simulé. Les tests n’exigent ni identifiants Intuis ni équipement physique. Les
sockets réseau sont interdites par défaut ; les sockets Unix d’asyncio restent
permises. Les fichiers et bases créés par les fixtures résident dans `tmp_path`.

## Matrice reproductible

| Home Assistant | Python | Contraintes |
|---|---|---|
| 2024.6.4 | 3.12 | `requirements/constraints-ha-2024.6.txt` |
| 2026.10.4 | >=3.14.2 | `requirements/constraints-ha-2026.10.txt` |

Depuis un environnement préparé selon [docs/development.md](../docs/development.md) :

```sh
python -m pip check
python -m pytest
python -m ruff check .
python -m pytest tests/unit/test_schedule_mutations.py -q
python -m pytest tests/unit/test_history_import.py -q
```

La CI exécute la suite complète et Ruff sur les deux environnements. Les résultats
locaux ne doivent pas être présentés comme une exécution de CI distante. Le nombre
de tests est un inventaire de cas, pas une mesure de couverture de lignes.

## Inventaire des contrats

| Fichier | Point d’entrée et garantie |
|---|---|
| `harness/test_native_fixtures.py` | Registry de services et schéma actifs, Store réel, transaction SQLite et transport aiohttp simulé |
| `unit/test_api_energy.py` | Vrai client HTTP : retry 401 fidèle/borné, erreurs typées, zéro valide, cache par pièce et disponibilité des agrégats |
| `unit/test_heating_reconciliation.py` | Commande climate → mapping/coordinateur → Store, identité du dictionnaire, confirmation/expiration, concurrence et retrait |
| `unit/test_history_import.py` | Vrai worker recorder/SQLite/compilateur sensor : commit, rollback, idempotence, baselines, couverture et arrêt pendant fetch/INSERT/Store |
| `unit/test_schedule_mutations.py` | Transformation d’une semaine entière, vrais services et number : demi-degrés, erreurs et mutations concurrentes |
| `unit/test_multi_home_services.py` | Cinq services via HA : cibles, noms courants, défauts, ajout/retrait, acquittements tardifs et composant en lecture seule |
| `unit/test_compatibility.py` | Vrais setup → unload → setup, factories d’entités et registry : IDs, données/options/version et Store inchangés ; migration native et client HTTP multi-domicile |
| `unit/test_climate.py`, `unit/test_overrides.py` | Régressions unitaires complémentaires des modes, commandes et prolongations |
| `unit/test_intuis_home.py`, `unit/test_intuis_schedule.py` | Parsing des modèles cloud |
| `unit/test_schedule_helpers.py` | Helpers de transformation et de recherche du planning |
| `unit/test_multi_home.py` | Config flow, migration et validation API : appels du code de production avec frontières simulées |

Les anciens tests `test_services.py` appelaient leurs propres mocks ou recopiaient
parsing et calculs : ils ont été supprimés après ajout des tests par services
réellement enregistrés. Les assertions de signature, d’existence de méthode ou de
présence de clés dans un dictionnaire construit dans le test ont été remplacées
par les parcours HTTP et de rechargement de `test_compatibility.py`.

## Fixtures et règles d’écriture

- `ha_hass` / `ha_entry_factory` : instance HA et entrées natives sans démarrer un compte cloud.
- `cloud_responses` : vrais `ClientResponse` via aioresponses ; toute URL non déclarée échoue.
- `frozen_clock` : horloge murale contrôlée en gardant l’horloge asyncio fonctionnelle.
- `recorder_session_factory` : tables recorder/transactions SQLite, sans worker.
- `live_recorder` dans `test_history_import.py` : thread, queue et schéma recorder réels.

Les mocks doivent rester aux frontières HTTP, chargement des plateformes ou erreur
injectée. Un test de service passe par `hass.services.async_call(..., blocking=True)`
pour couvrir aussi le schéma. Un test recorder attend l’acquittement du travail,
pas seulement sa mise en file. Les invariants d’identifiants sont lus sur les
entités créées par les factories de production et dans le registry, sans recopier
leur formule dans le test. Les tests de rechargement conservent les mêmes clés et
versions de stockage et n’exigent aucune migration implicite.

## Limites explicites

La suite valide les contrats de l’intégration sur deux versions HA précises ; elle
ne garantit ni disponibilité ni comportement de l’API Intuis réelle. Les imports
avec séries non alignées sur les jours locaux ou sans baseline live valide sont
refusés sans mutation. Les verrous de planning n’arbitrent pas les modifications
concurrentes de l’application externe. Voir les documents métier pour ces limites.
