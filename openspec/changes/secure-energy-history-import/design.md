# Design

## Context

history_import.py, __init__.py, services.py, tests/unit/test_history_import.py ; adaptateur recorder et tests de cycle de vie à créer.

La motivation et les contrats sont décrits dans proposal.md et specs/. Les dépendances sont précisées dans le plan global.

## Goals / Non-Goals

**Goals:** rendre les contrats spécifiés testables et fiables en préservant les identifiants et les données existantes.

**Non-Goals:** ajouter de nouvelles fonctions produit, modifier les équipements réels ou lancer un import cloud pendant la planification.

## Decisions

1. Découper l’import en récupération, validation/staging, puis remplacement ; valider les timestamps, unités, valeurs finies, doublons et couverture avant mutation. Une série vide ne constitue pas une preuve de consommation nulle.

2. Isoler le recorder dans un adaptateur. Exiger un remplacement atomique dans un job recorder avec transaction, ou refuser explicitement le remplacement destructif si la version HA ne le permet pas. Ne pas enchaîner suppression SQL commitée et import mis en file sans garantie commune.

3. Préserver les baselines et contrôler les bornes horaires et le fuseau du domicile, y compris les changements d’heure. Un réimport du même jeu de données ne doit pas additionner deux fois l’énergie.

4. Conserver une référence à la tâche d’import, sérialiser les imports par entrée, annuler et attendre sa terminaison au déchargement. Publier les statuts seulement après confirmation de l’écriture.

## Risks / Trade-offs

Les API recorder varient selon HA : tester la version minimale retenue et la version courante supportée ; en absence de garantie transactionnelle, retourner une erreur sans suppression. Les transactions volumineuses exigent des bornes par pièce et une validation en mémoire avant leur ouverture.

## Migration Plan

1. Établir les tests de régression sur les contrats existants et le cas défaillant.
2. Implémenter le changement avec les tests du lot ; maintenir les identifiants publics et formats persistés, ou fournir une migration explicitement testée.
3. Exécuter les contrôles ciblés puis la suite et la matrice supportée.
4. Documenter les changements de comportement et les limites de compatibilité.
5. En cas de régression, revenir à la version de code précédente ; ne jamais supprimer les données utilisateur pour effectuer ce retour. Une transaction recorder déjà confirmée ne s’annule pas par simple rollback du code.

## Implemented recorder contract

- `RecorderTask.run` and `queue_task` are exercised with the actual recorder worker
  in HA 2024.6.4 and HA 2026.10.4. One SQLAlchemy session/transaction owns reads,
  deletion, insertion and cumulative-sum adjustment. The coroutine waits for a
  Future acknowledged after commit/rollback on the recorder thread.
- Import complete days in the domicile timezone, excluding today's partial day.
  Require exact, unique local-midnight coverage; zero is valid and gaps are refused.
  DST boundaries follow calendar days; non-hour-aligned boundaries are refused.
- Require existing kWh metadata and a finite post-period short-term anchor. Without
  one, refuse without mutation and instruct the user to let live sensor statistics
  record before retrying. This also applies to the automatic setup attempt.
- Preserve the newest anchor ID and all post-period states/timestamps. Shift sums
  by the new minus old cumulative boundary, using the most recent hourly or
  short-term boundary row; never treat a daily state as a per-interval delta.
- No metadata changes are performed, so metadata caches remain valid. The latest
  short-term ID survives deletion; the real HA sensor compiler is tested to
  continue from its adjusted baseline.
- Reject inactive/unsupported workers before queueing. Cancellation drains the
  transaction acknowledgement before unload completes, including cancellation
  during an INSERT. Clear task ownership after direct awaited imports, and avoid
  reloading when only the consumed one-shot import option is cleared.
- The previous standalone delete and post-import adjustment helpers were removed.
  Their mock-only tests were replaced by tests of the importer and real worker.

Operational details and rollback limitations: [safe import documentation](../../../docs/08-safe-energy-history-import.md).
