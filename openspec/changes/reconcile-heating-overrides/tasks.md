# Tasks

Priorité : **P1/P2** — Review : **R2, R5**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../README.md) avant implémentation. Les tâches cochées sont implémentées et vérifiées sur les deux environnements HA.

## 1. Régressions et partage

- [x] 1.1 Corriger les fixtures qui utilisent overrides or {} et ajouter un parcours réel démarrage vide → commande climate → mise à jour IntuisData → sauvegarde.
- [x] 1.2 Conserver le dictionnaire partagé avec un test explicite de son identité, de la prolongation indéfinie et de la suppression à expiration.
- [x] 1.3 Couvrir le rechargement avec dérogations persistées et les échecs de commande sans mutation de succès.

## 2. Réconciliation des états

- [x] 2.1 Introduire une interface commune pour les intentions de dérogation et leur persistance, compatible avec le stockage actuel.
- [x] 2.2 Définir puis implémenter la confirmation et l’expiration bornée de l’état optimiste ; supprimer les caches permanents des modes HVAC/preset.
- [x] 2.3 Tester boost → auto, manuel → planning, modification depuis Intuis et confirmation retardée/échouée via le vrai callback du coordinateur.
- [x] 2.4 Annuler ou remplacer les minuteries d’expiration et les nettoyer au retrait de l’entité et au déchargement.

## 3. Validation

- [x] 3.1 Exécuter les tests climate, overrides et rechargement, puis la suite complète.
- [x] 3.2 Documenter la source des états, le comportement indéfini et la persistance sans modifier les unique_id.


## Validation — 26 octobre 2026

- **257 tests passent** sur HA 2024.6.4 / Python 3.12.14 et HA 2026.10.4 / Python 3.14.4.
- 16 nouveaux cas dans `tests/unit/test_heating_reconciliation.py` emploient le vrai mapping IntuisData, DataUpdateCoordinator, Store sur disque et le cycle de vie des entités ; le test obsolète du getter de callback supprimé a été remplacé par des sauvegardes observées.
- Cas vérifiés : dictionnaire vide partagé, prolongation et expiration persistées, recréation depuis le stockage, refus API, confirmation puis modification externe, refresh échoué et délai local, expiration distante distincte, remplacement/annulation des minuteries, acquittement tardif après retrait, disque en erreur après API acceptée, commande concurrente à une prolongation et protection contre un ancien snapshot.
- Ruff sur les deux environnements et `git diff --check` passent. Les tests n’ouvrent aucune connexion Intuis réelle.
- Source des états et limites d’observabilité documentées dans [docs/09-heating-overrides.md](../../../docs/09-heating-overrides.md). Identifiants, options et format de stockage inchangés.
