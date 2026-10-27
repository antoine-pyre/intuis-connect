# Proposal

## Why

Le remplacement d’une plage conserve des transitions internes qui interrompent la zone demandée. Les températures de planning sont tronquées malgré un pas affiché de 0,5 °C.

Priorité : **P1/P2**. Traçabilité : **R3, R7**, voir le [plan global](../../../README.md).

## What Changes

- Remplacer effectivement l’intervalle demandé, y compris à cheval sur la semaine.
- Restaurer la zone initialement prévue à la borne de fin et préserver le reste du planning.
- Conserver les températures décimales dans les deux chemins d’écriture.
- Appliquer les mutations locales uniquement après confirmation API.

## Capabilities

### New Capabilities

- `heating-schedules` : Édition fiable des plages et températures des plannings.

### Modified Capabilities

Aucune : le dépôt ne dispose pas encore de spécifications de référence. Les nouvelles capabilities formalisent les contrats attendus de fonctions existantes.

## Impact

timetable.py, services.py, number.py, entity/intuis_schedule.py, tests/unit/test_schedule_helpers.py, tests/unit/test_services.py ; tests number à créer.

Dépendances et ordre de livraison : voir le plan global. Ce changement prépare les travaux ; aucune tâche d’implémentation n’est considérée comme réalisée.
