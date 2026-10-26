# Proposal

## Why

Les coûts, le prix historique et leur recalcul sont absents du projet. Le code proposé par #22 fournit une base fonctionnelle, mais comporte des défauts de configuration, migration et publication.

Traçabilité : [plan d’intégration](../../../docs/pr-integration-plan.md) et [comparaison complète](../../../docs/pr-comparison-current-2026-10-26.md).

## What Changes

- Ajouter des coûts par pièce et domicile avec prix fixe ou entité HA et historique explicite.
- Fournir une série statistique de coût et un capteur d’affichage distincts de l’énergie existante.
- Ajouter un recalcul ciblé, idempotent et non destructif.

## Capabilities

### New Capabilities

- `energy-cost-statistics` : Ajouter les coûts énergétiques.

### Modified Capabilities

Aucune spécification de référence archivée n’est modifiée ; les contrats du socle en cours restent requis.

## Impact

nouveau cost_stats.py, capteurs coût, config_flow, recorder, services, traductions et tests ; source TheFab21 #22/#24.

Dépendances : Contrat horaire validé dans add-hourly-energy-statistics ; attribution.

État : planifié uniquement, aucune fonction annoncée comme livrée.
