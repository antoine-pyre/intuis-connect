# Proposal

## Why

L’import efface les statistiques existantes avant de récupérer leurs remplaçantes. Une panne, une réponse vide ou une annulation peut perdre des données et produire un statut completed trompeur.

Priorité : **P1**. Traçabilité : **R1**, voir le [plan global](../../../README.md).

## What Changes

- Préparer et valider les mesures avant toute mutation des statistiques.
- Remplacer les données avec une garantie de restauration en cas d’échec et conserver les statistiques hors intervalle.
- Rendre les réimports idempotents et les états d’échec, d’annulation et de succès explicites.
- Rattacher les imports au cycle de vie de l’entrée pour arrêter les traitements au déchargement.

## Capabilities

### New Capabilities

- `energy-history-import` : Import et remplacement fiables des statistiques énergétiques.

### Modified Capabilities

Aucune : le dépôt ne dispose pas encore de spécifications de référence. Les nouvelles capabilities formalisent les contrats attendus de fonctions existantes.

## Impact

history_import.py, __init__.py, services.py, tests/unit/test_history_import.py ; adaptateur recorder et tests de cycle de vie à créer.

Dépendances et ordre de livraison : voir le plan global. Ce changement prépare les travaux ; aucune tâche d’implémentation n’est considérée comme réalisée.
