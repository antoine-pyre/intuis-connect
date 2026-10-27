# Proposal

## Why

Les tests de certains services exercent leurs mocks ou recopient la logique attendue. La CI ne lance pas Ruff et les dépendances ainsi que la compatibilité HA ne définissent pas un environnement de validation reproductible.

Priorité : **P2/transverse**. Traçabilité : **Q1, Q2, Q3**, voir le [plan global](../../../README.md).

## What Changes

- Établir une base de tests reproductible et tester les vrais points d’entrée.
- Rendre Ruff et les régressions bloquants en CI.
- Réduire services.py et les duplications après sécurisation des comportements.
- Aligner documentation, versions supportées et environnements de développement.

## Capabilities

### New Capabilities

- `development-validation` : Contrat de validation reproductible pour les contributions.

### Modified Capabilities

Aucune : le dépôt ne dispose pas encore de spécifications de référence. Les nouvelles capabilities formalisent les contrats attendus de fonctions existantes.

## Impact

requirements_dev.txt, pytest.ini, .github/workflows/tests.yml, .devcontainer/devcontainer.json, tests/conftest.py, tests/PLAN.md, services.py, number.py, intuis_data.py, docs/, README.md ; configuration Ruff et modules métier à créer.

Dépendances et ordre de livraison : voir le plan global. Ce changement prépare les travaux ; aucune tâche d’implémentation n’est considérée comme réalisée.
