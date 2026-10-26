# Tasks

Priorité : **P1/P2** — Review : **R3, R7**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../README.md) avant implémentation. Toutes les tâches restent à faire.

## 1. Tests des contrats

- [ ] 1.1 Ajouter le cas Eco 07:00–11:00 avec transitions à 08:00 et 10:00 en appelant le handler enregistré.
- [ ] 1.2 Couvrir plages multi-jours, dimanche–lundi, fin à minuit, bornes exactes et plannings sans offset zéro ; vérifier l’invariance hors intervalle.
- [ ] 1.3 Ajouter des tests des deux points d’entrée avec 19,5 °C et un échec API sans mutation locale.

## 2. Transformations et écriture

- [ ] 2.1 Implémenter une transformation pure du planning hebdomadaire avec suppression des transitions internes et restauration de la zone de fin.
- [ ] 2.2 Normaliser offsets, ordre et transitions consécutives ; valider les plages invalides et documenter les cas de minuit.
- [ ] 2.3 Supprimer les conversions int des températures et aligner types, validation, payloads et caches sur le pas de 0,5 °C.
- [ ] 2.4 Mutualiser la construction des payloads et sérialiser les modifications d’un même planning.
- [ ] 2.5 Publier la copie locale modifiée seulement après succès API, pour services et number.

## 3. Validation

- [ ] 3.1 Exécuter les tests de transformation, handlers et number, puis la suite complète.
- [ ] 3.2 Mettre à jour les exemples de modification de plages et les garanties de précision/échec.
