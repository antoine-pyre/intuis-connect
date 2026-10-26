# Tasks

Priorité : **P1** — Review : **R1**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../README.md) avant implémentation. Toutes les tâches restent à faire.

## 1. Contrat recorder et tests de régression

- [ ] 1.1 Vérifier les API recorder des versions HA retenues et documenter le mécanisme de transaction, de confirmation et le refus sûr des versions incompatibles.
- [ ] 1.2 Ajouter des tests sur le véritable importeur : panne réseau, réponse vide, limitation API et annulation ; vérifier que les statistiques existantes restent intactes.
- [ ] 1.3 Ajouter des tests recorder avec base temporaire pour baselines, données hors intervalle, réimport identique, échec d’écriture et jours avec zéro valide.

## 2. Implémentation sûre

- [ ] 2.1 Extraire un adaptateur recorder et séparer récupération, validation, préparation des statistiques et remplacement.
- [ ] 2.2 Implémenter le remplacement transactionnel validé et le refus sans suppression lorsque la garantie ne peut pas être assurée.
- [ ] 2.3 Corriger les sommes cumulées, la couverture, les limites de période et la gestion des jours locaux/changements d’heure.
- [ ] 2.4 Corriger les statuts terminaux et les résultats partiels ; ne déclarer completed qu’après confirmation du succès attendu.
- [ ] 2.5 Stocker les tâches d’import et sérialiser leur exécution ; annuler puis attendre leur arrêt dans async_unload_entry.

## 3. Validation et livraison

- [ ] 3.1 Exécuter les tests import/recorder/cycle de vie, puis la suite complète ; vérifier l’absence d’écriture après unload.
- [ ] 3.2 Mettre à jour la documentation de l’import, des erreurs, de la compatibilité et du retour arrière ; conserver les identifiants des capteurs.
