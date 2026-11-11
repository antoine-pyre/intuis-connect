# Proposal

## Why

L’éditeur HTML de TheFab21 et sa distribution automatique #24 sont absents. Ils doivent consommer les services actuels étendus plutôt que réintroduire les anciens handlers et capteurs.

Traçabilité : [plan d’intégration](../../../../docs/pr-integration-plan.md) et [comparaison complète](../../../../docs/pr-comparison-current-2026-10-26.md).

## What Changes

- Adapter la grille hebdomadaire, les zones, les horaires et la sauvegarde de l’éditeur source.
- Servir le fichier embarqué à /api/intuis_connect/planning avec gestion de cache/version.
- Conserver les modes intégré et navigateur autonome, avec configuration explicite et affichage des erreurs.

## Capabilities

### New Capabilities

- `bundled-planning-ui` : Ajouter l’éditeur de planning embarqué.

### Modified Capabilities

Aucune spécification de référence archivée n’est modifiée ; les contrats du socle en cours restent requis.

## Impact

resources/intuis_planning.html et éventuels fichiers UI isolés, module de vue HTTP, __init__.py, manifest, exemples et tests HTTP/JS ; source TheFab21 #17/#22/#24.

Dépendances : extend-schedule-editing et attribution ; aucune dépendance au calcul d’énergie ou de coûts.

État : planifié uniquement, aucune fonction annoncée comme livrée.
