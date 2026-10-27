# Proposal

## Why

Les handlers lisent home_id alors que leurs schémas le rejettent. Les options des services sont figées sur le premier domicile et la génération dynamique écrit dans le répertoire du composant.

Priorité : **P2**. Traçabilité : **R6**, voir le [plan global](../../../README.md).

## What Changes

- Accepter et valider home_id sur tous les services qui le prennent en charge.
- Rendre accessibles les plannings, zones et pièces de chaque domicile après ajout/rechargement/refresh.
- Conserver les défauts existants sans home_id et rendre les erreurs explicites.
- Remplacer la réécriture de services.yaml à l’exécution par des descriptions statiques et une validation métier sur les données courantes.

## Capabilities

### New Capabilities

- `multi-home-services` : Services adressables par domicile et validés sur les données actuelles.

### Modified Capabilities

Aucune : le dépôt ne dispose pas encore de spécifications de référence. Les nouvelles capabilities formalisent les contrats attendus de fonctions existantes.

## Impact

services.py, services.yaml, __init__.py, translations/en.json, translations/fr.json, tests/unit/test_multi_home.py, tests/unit/test_services.py.

Dépendances et ordre de livraison : voir le plan global. Ce changement prépare les travaux ; aucune tâche d’implémentation n’est considérée comme réalisée.
