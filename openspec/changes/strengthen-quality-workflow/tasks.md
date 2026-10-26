# Tasks

Priorité : **P2/transverse** — Review : **Q1, Q2, Q3**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../README.md) avant implémentation. Les cases cochées correspondent aux travaux validés ; les groupes 2 et 3 restent à faire.

## 1. Socle à réaliser avant les correctifs

- [x] 1.1 Relever la compatibilité réelle Python/HA et les résultats initiaux pytest/Ruff dans des environnements isolés ; distinguer erreurs préexistantes et nouvelles régressions.
- [x] 1.2 Créer des contraintes de dépendances versionnées pour les versions HA minimale et courante retenues et documenter les commandes locales.
- [x] 1.3 Préparer un harness HA pour services enregistrés, config entries, stockage et recorder, avec horloge et transport simulés fidèlement.
- [x] 1.4 Ajouter une configuration Ruff explicite et les checks CI de tests/lint ; corriger le socle nécessaire sans reporter les P1 à un refactoring global.

## 2. Refactoring après les correctifs

- [ ] 2.1 Extraire de services.py la résolution des cibles et les opérations métier couvertes ; conserver les noms et schémas publics.
- [ ] 2.2 Mutualiser les payloads de planning et la gestion des dérogations sans introduire de seconde source d’état.
- [ ] 2.3 Remplacer les tests de mocks ou de logique recopiée par les régressions des vrais points d’entrée ; supprimer uniquement les assertions devenues redondantes.
- [ ] 2.4 Aligner annotations et structures partagées, nettoyer imports/code mort et réduire les exceptions trop larges dans les chemins critiques.

## 3. Validation et documentation

- [ ] 3.1 Exécuter la matrice Python/HA retenue et Ruff ; conserver les résultats et les limites réellement vérifiées.
- [ ] 3.2 Actualiser tests/PLAN.md, docs d’architecture, valeurs par défaut du README, instructions développeur et devcontainer.
- [ ] 3.3 Vérifier la compatibilité des unique_id, entity_id, configuration et stockage sur rechargement ; aucune migration implicite de données.
- [ ] 3.4 Mettre à jour les minima README/hacs.json uniquement si les tests justifient un changement, et publier une note de compatibilité explicite.

## Validation du socle — 26 octobre 2026

- Installation vierge HA 2024.6.4 / Python 3.12.14 avec le fichier de contraintes : réussie ; cohérence des dépendances vérifiée.
- HA 2026.10.4 / Python 3.14.4 : résolution des contraintes et cohérence des dépendances vérifiées.
- `python -m pytest` avec sockets externes interdites : **197 tests passent** sur chaque environnement (193 existants + 4 smoke tests natifs).
- `python -m ruff check .` et `git diff --check` : réussis.
- Détail des baselines et limites du harness : [docs/development.md](../../../docs/development.md).
- Le worker recorder et les modifications fonctionnelles restent à vérifier dans les lots dédiés ; le smoke SQLite valide les transactions, pas la queue du worker.
