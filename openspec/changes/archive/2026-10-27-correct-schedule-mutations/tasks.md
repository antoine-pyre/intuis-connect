# Tasks

Priorité : **P1/P2** — Review : **R3, R7**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../../README.md) avant implémentation. Toutes les tâches ci-dessous sont implémentées et validées sur les deux environnements HA.

## 1. Tests des contrats

- [x] 1.1 Ajouter le cas Eco 07:00–11:00 avec transitions à 08:00 et 10:00 en appelant le handler enregistré.
- [x] 1.2 Couvrir plages multi-jours, dimanche–lundi, fin à minuit, bornes exactes et plannings sans offset zéro ; vérifier l’invariance hors intervalle.
- [x] 1.3 Ajouter des tests des deux points d’entrée avec 19,5 °C et un échec API sans mutation locale.

## 2. Transformations et écriture

- [x] 2.1 Implémenter une transformation pure du planning hebdomadaire avec suppression des transitions internes et restauration de la zone de fin.
- [x] 2.2 Normaliser offsets, ordre et transitions consécutives ; valider les plages invalides et documenter les cas de minuit.
- [x] 2.3 Supprimer les conversions int des températures et aligner types, validation, payloads et caches sur le pas de 0,5 °C.
- [x] 2.4 Mutualiser la construction des payloads et sérialiser les modifications d’un même planning.
- [x] 2.5 Publier la copie locale modifiée seulement après succès API, pour services et number.

## 3. Validation

- [x] 3.1 Exécuter les tests de transformation, handlers et number, puis la suite complète.
- [x] 3.2 Mettre à jour les exemples de modification de plages et les garanties de précision/échec.

## Validation — 26 octobre 2026

- **299 tests passent** sur HA 2024.6.4 / Python 3.12.14 et HA 2026.10.4 / Python 3.14.4.
- **42 nouveaux cas** dans `tests/unit/test_schedule_mutations.py` : semaine complète,
  input immuable, transitions internes, bornes exactes, semaine cyclique, minuit,
  absence d’offset zéro, handlers natifs et alias `day`, précision 19,5 °C,
  erreurs API sans mutation, validation des températures et éditions concurrentes.
- Les tests interdisent le réseau externe ; les seules commandes API sont simulées.
- Ruff et `git diff --check` passent ; OpenSpec strict valide les six changements.
- Documentation actualisée : [gestion des plannings](../../../../docs/07-schedule-management.md).
- Aucun changement d’identifiant, de configuration ni de format de stockage.
