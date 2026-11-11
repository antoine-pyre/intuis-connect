# Proposal

## Why

Le projet ne permet pas encore de remplacer un timetable complet par service, de cibler un planning inactif pour ses créneaux ni de régler ses températures away/hg. Les renommages et données UI des PRs restent aussi utiles.

Traçabilité : [plan d’intégration](../../../../docs/pr-integration-plan.md) et [comparaison complète](../../../../docs/pr-comparison-current-2026-10-26.md).

## What Changes

- Étendre set_schedule_slot aux plannings nommés ou identifiés, en conservant le défaut actif.
- Ajouter sync_schedule pour le timetable complet et les températures absence/hors-gel.
- Actualiser les libellés de calendrier/number après renommage et enrichir les summaries existants pour l’UI.

## Capabilities

### New Capabilities

- `extended-schedule-editing` : Étendre les services et données de planning.

### Modified Capabilities

Aucune spécification de référence archivée n’est modifiée ; les contrats du socle en cours restent requis.

## Impact

schedule_mutations.py, service_targets.py, services.py/yaml, number.py, calendar.py, entity/intuis_home_entity.py, timetable.py et traductions/tests ; sources TheFab21 #17/#22/#24.

Dépendances : Socle correct-schedule-mutations et fix-multi-home-service-contracts ; attribution ; indépendant de l’énergie.

État : planifié uniquement, aucune fonction annoncée comme livrée.
