# Tasks

Priorité : **P2** — Review : **R6**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../README.md) avant implémentation. Toutes les tâches restent à faire.

## 1. Tests des vrais points d’entrée

- [ ] 1.1 Enregistrer les vrais services dans un harness HA et les appeler via hass.services.async_call avec les schémas actifs.
- [ ] 1.2 Tester home_id pour chaque service, deux domiciles avec noms identiques, cible inconnue et absence de commande sur l’autre domicile.
- [ ] 1.3 Tester les défauts sans cible, le champ historique day, ajout/rechargement d’entrée et refresh des plannings.

## 2. Schémas, descriptions et cycle de vie

- [ ] 2.1 Ajouter home_id optionnel dans les schémas et centraliser la résolution des entrées et les erreurs retournées à l’appelant.
- [ ] 2.2 Remplacer les options de noms figées par des champs validés sur les données courantes du domicile ciblé.
- [ ] 2.3 Retirer la génération de services.yaml et ses appels ; fournir des descriptions statiques cohérentes avec les schémas et traductions.
- [ ] 2.4 Préserver les défauts sans cible et la compatibilité day/start_day/end_day ; documenter l’avertissement de choix implicite.
- [ ] 2.5 Tester et corriger l’enregistrement/désenregistrement avec plusieurs entrées, y compris le retrait de la première et de la dernière.

## 3. Validation

- [ ] 3.1 Vérifier setup et refresh avec répertoire du composant en lecture seule ; exécuter les tests services/multi-home puis la suite complète.
- [ ] 3.2 Mettre à jour les exemples YAML et la documentation des paramètres et des sélecteurs.
