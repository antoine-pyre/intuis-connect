# Proposal

## Why

Une nouvelle tentative après HTTP 401 perd des paramètres de transport et peut changer de serveur. Les erreurs de mesure deviennent des zéros mis en cache pour la journée.

Priorité : **P1/P2**. Traçabilité : **R4, R8**, voir le [plan global](../../README.md).

## What Changes

- Conserver URL complète, query, payload, en-têtes et timeout sur la nouvelle tentative après 401.
- Limiter la réauthentification et la répétition pour éviter les boucles.
- Distinguer mesure valide nulle, donnée absente et erreur par pièce.
- Mettre en cache uniquement les résultats valides et retenter les pièces en échec.

## Capabilities

### New Capabilities

- `cloud-requests` : Requêtes cloud et réauthentification conservant leur destination.
- `energy-measurements` : Mesures énergétiques valides et récupération des indisponibilités.

### Modified Capabilities

Aucune : le dépôt ne dispose pas encore de spécifications de référence. Les nouvelles capabilities formalisent les contrats attendus de fonctions existantes.

## Impact

intuis_api/api.py, intuis_data.py, sensor.py ; tests client HTTP et cache à créer.

Dépendances et ordre de livraison : voir le plan global. Ce changement prépare les travaux ; aucune tâche d’implémentation n’est considérée comme réalisée.
