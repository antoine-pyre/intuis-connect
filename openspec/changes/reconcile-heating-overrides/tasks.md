# Tasks

Priorité : **P1/P2** — Review : **R2, R5**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../README.md) avant implémentation. Toutes les tâches restent à faire.

## 1. Régressions et partage

- [ ] 1.1 Corriger les fixtures qui utilisent overrides or {} et ajouter un parcours réel démarrage vide → commande climate → mise à jour IntuisData → sauvegarde.
- [ ] 1.2 Conserver le dictionnaire partagé avec un test explicite de son identité, de la prolongation indéfinie et de la suppression à expiration.
- [ ] 1.3 Couvrir le rechargement avec dérogations persistées et les échecs de commande sans mutation de succès.

## 2. Réconciliation des états

- [ ] 2.1 Introduire une interface commune pour les intentions de dérogation et leur persistance, compatible avec le stockage actuel.
- [ ] 2.2 Définir puis implémenter la confirmation et l’expiration bornée de l’état optimiste ; supprimer les caches permanents des modes HVAC/preset.
- [ ] 2.3 Tester boost → auto, manuel → planning, modification depuis Intuis et confirmation retardée/échouée via le vrai callback du coordinateur.
- [ ] 2.4 Annuler ou remplacer les minuteries d’expiration et les nettoyer au retrait de l’entité et au déchargement.

## 3. Validation

- [ ] 3.1 Exécuter les tests climate, overrides et rechargement, puis la suite complète.
- [ ] 3.2 Documenter la source des états, le comportement indéfini et la persistance sans modifier les unique_id.
