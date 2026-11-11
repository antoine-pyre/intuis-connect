# Proposal

## Why

Les adaptations des PRs pourraient masquer l’origine du code et des idées si elles sont livrées sous de nouveaux commits. Les liens documentaires du dépôt restent également incohérents.

Traçabilité : [plan d’intégration](../../../../docs/pr-integration-plan.md) et [comparaison complète](../../../../docs/pr-comparison-current-2026-10-26.md).

## What Changes

- Créer un registre durable des auteurs, PRs, commits sources, fonctionnalités et statut de reprise.
- Relier README, notes de version, descriptions de livraison et commits adaptés à ce registre.
- Harmoniser les liens d’installation et préserver les mentions de licence et notices présentes dans les sources reprises.

## Capabilities

### New Capabilities

- `contribution-provenance` : Conserver le crédit des contributions.

### Modified Capabilities

Aucune spécification de référence archivée n’est modifiée ; les contrats du socle en cours restent requis.

## Impact

README.md, CONTRIBUTORS.md, docs/pr-integration-plan.md et journal de provenance ; aucun changement Python.

Dépendances : Premier lot, puis attribution complétée dans chaque lot fonctionnel.

État : planifié uniquement, aucune fonction annoncée comme livrée.
