# Développement et validation

La matrice de validation conserve le minimum annoncé **HA 2024.6** et vérifie
également **HA 2026.10.4**, version courante constatée dans les métadonnées PyPI
le 26 octobre 2026. Les fichiers de contraintes sont des instantanés complets des
dépendances de test, distincts des dépendances runtime gérées par Home Assistant.

| Environnement | Python | Home Assistant | Contraintes |
|---|---|---|---|
| Minimum | 3.12 | 2024.6.4 | `requirements/constraints-ha-2024.6.txt` |
| Courant | >=3.14.2 | 2026.10.4 | `requirements/constraints-ha-2026.10.txt` |

Pour le minimum, avec Python 3.12 installé :

```sh
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements_dev.txt -c requirements/constraints-ha-2024.6.txt
.venv/bin/python -m pip check
.venv/bin/python -m pytest
.venv/bin/python -m ruff check .
```

Pour la version courante, créer un autre environnement avec Python 3.14.2 ou plus,
puis utiliser `requirements/constraints-ha-2026.10.txt` dans les mêmes commandes.
Le devcontainer utilise le minimum Python 3.12 ; la CI vérifie les deux versions.
Les tests désactivent les sockets réseau et autorisent les sockets Unix nécessaires
à asyncio. Aucun compte ni équipement Intuis n’est nécessaire. Les réponses HTTP
simulées passent par `aioresponses`, pas par un mock approximatif de ClientResponse.
Sur aiohttp 3.14, la fixture fournit le nouvel argument constructeur `stream_writer` (compteur synthétique à zéro)
que aioresponses 0.7.9 omet ; les instances retournées restent de vrais ClientResponse.

Mettre à jour explicitement les versions HA, les dépendances et leurs contraintes,
puis vérifier les deux environnements avant de committer un nouvel instantané.
Ne pas installer la version courante de HA avec Python 3.12 : son interpréteur
minimal est différent. Installer les dépendances normalement, sans `--no-deps`.

## Fixtures natives

Les anciens tests unitaires conservent leurs mocks. Les nouveaux tests peuvent
utiliser les fixtures suivantes de `tests/conftest.py` :

- `ha_hass` : vraie instance HA, registry de services, boucle asyncio et répertoire temporaire.
- `ha_entry_factory` : vraies config entries enregistrées, sans démarrer l’intégration cloud.
- `recorder_session_factory` : sessions SQLite réelles avec les tables de la version HA installée.
- `cloud_responses` : transport aiohttp simulé ; les requêtes non déclarées échouent.
- `frozen_clock` : horloge murale figée, avec horloge asyncio réelle.

Les smoke tests de `tests/harness/` exercent le véritable handler de refresh via
le registry et son schéma, le Store HA sur disque, une transaction et un rollback
sur les tables recorder, ainsi que le transport HTTP. L’écriture de `services.yaml`
est isolée dans ce test pour éviter de modifier les sources pendant les tests.

La fixture SQLite **ne lance pas le worker recorder** et ne prouve pas le
fonctionnement des imports mis en file. Les tests de `test_history_import.py`
lancent séparément le véritable thread/worker recorder, ses sessions et sa queue,
attendent son initialisation puis les acquittements de transaction. Ils vérifient
également la compilation live HA après import, le rollback SQL et le déchargement
pendant un INSERT et une sauvegarde de progression Store.

## Baseline du 26 octobre 2026

Avant changements du produit : HA 2026.10.4 exécutait les **193 tests existants**.
L’environnement HA 2024.6.4 échouait à la collecte avec des dépendances transitives
historiques non bornées (`josepy`, puis l’import de `session_scope`). Les contraintes
fixent notamment `josepy==1.14.0`, `pycares==4.4.0` et `habluetooth==0.11.0`.
Le fallback de `session_scope` conserve le chemin historique de HA 2024.6.
Après ce correctif de compatibilité, les 193 tests passent aussi sur le minimum.
Ruff signalait initialement 40 défauts d’imports et variables inutilisés ; ils
ont été corrigés sans refonte métier. La configuration active les règles de
correction `E4`, `E7`, `E9` et `F` sur tout le dépôt, sans exclusions par fichier.
Les extensions de règles et le refactoring restent dans le lot de consolidation.

Validation du socle : **197 tests passent** sur chaque environnement (193 tests
existants et 4 smoke tests natifs). Ruff et la vérification de cohérence des
dépendances passent également. Les nouveaux contrôles CI sont configurés ; leur
exécution distante n’a pas encore eu lieu. Dans le sandbox desktop, les réveils
de threads/executor peuvent être bloqués : les tests natifs ont été exécutés
avec les primitives locales autorisées, en conservant l’interdiction des sockets
externes via pytest-socket.
