# Proposal

## Why

Un dictionnaire de dérogations initialement vide est remplacé dans IntuisData. Les attributs optimistes climate peuvent ensuite masquer indéfiniment le retour d’état cloud.

Priorité : **P1/P2**. Traçabilité : **R2, R5**, voir le [plan global](../../../README.md).

## What Changes

- Conserver une source partagée des dérogations, même quand elle est vide.
- Rendre la prolongation, l’expiration et la persistance cohérentes.
- Limiter l’état optimiste à l’attente du retour cloud et refléter les changements externes.
- Nettoyer les callbacks de rafraîchissement à l’expiration et au déchargement.

## Capabilities

### New Capabilities

- `heating-overrides` : Dérogations persistées et prolongées de façon cohérente.
- `climate-state` : État climate réconcilié avec le retour des équipements.

### Modified Capabilities

Aucune : le dépôt ne dispose pas encore de spécifications de référence. Les nouvelles capabilities formalisent les contrats attendus de fonctions existantes.

## Impact

intuis_data.py, climate.py, __init__.py, tests/conftest.py, tests/unit/test_overrides.py, tests/unit/test_climate.py.

Dépendances et ordre de livraison : voir le plan global. Ce changement prépare les travaux ; aucune tâche d’implémentation n’est considérée comme réalisée.
