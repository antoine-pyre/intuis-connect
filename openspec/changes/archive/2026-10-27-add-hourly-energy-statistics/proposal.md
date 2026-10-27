# Proposal

## Why

Le scale 1hour actuel ne fournit pas un import historique horaire ni un updater de statistiques horaires exactes. #17 et #22 proposent ces capacités mais réécrivent des garanties désormais acquises.

Traçabilité : [plan d’intégration](../../../../docs/pr-integration-plan.md) et [comparaison complète](../../../../docs/pr-comparison-current-2026-10-26.md).

## What Changes

- Ajouter un contrat de série horaire strict et des requêtes bornées, avec déduplication des chevauchements.
- Importer les heures closes dans une série statistique distincte et stable ; ajouter le rattrapage après interruption.
- Étendre le service d’historique à une granularité explicite, sans changer son défaut quotidien ni les capteurs existants.

## Capabilities

### New Capabilities

- `hourly-energy-statistics` : Ajouter les séries et statistiques horaires.

### Modified Capabilities

Aucune spécification de référence archivée n’est modifiée ; les contrats du socle en cours restent requis.

## Impact

intuis_api/api.py, history_import.py, recorder_import.py, nouveau module hourly_stats.py, __init__.py, config_flow.py, services et traductions, tests recorder/API ; sources #17/#22/#24, TheFab21.

Dépendances : Socle local f92e3e4 et attribution ; indépendant des services de planning.

État : planifié uniquement, aucune fonction annoncée comme livrée.
