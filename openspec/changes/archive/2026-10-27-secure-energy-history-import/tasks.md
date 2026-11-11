# Tasks

Priorité : **P1** — Review : **R1**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../../README.md) avant implémentation. Les tâches ci-dessous ont été implémentées et vérifiées sur les deux environnements HA.

## 1. Contrat recorder et tests de régression

- [x] 1.1 Vérifier les API recorder des versions HA retenues et documenter le mécanisme de transaction, de confirmation et le refus sûr des versions incompatibles.
- [x] 1.2 Ajouter des tests sur le véritable importeur : panne réseau, réponse vide, limitation API et annulation ; vérifier que les statistiques existantes restent intactes.
- [x] 1.3 Ajouter des tests recorder avec base temporaire pour baselines, données hors intervalle, réimport identique, échec d’écriture et jours avec zéro valide.

## 2. Implémentation sûre

- [x] 2.1 Extraire un adaptateur recorder et séparer récupération, validation, préparation des statistiques et remplacement.
- [x] 2.2 Implémenter le remplacement transactionnel validé et le refus sans suppression lorsque la garantie ne peut pas être assurée.
- [x] 2.3 Corriger les sommes cumulées, la couverture, les limites de période et la gestion des jours locaux/changements d’heure.
- [x] 2.4 Corriger les statuts terminaux et les résultats partiels ; ne déclarer completed qu’après confirmation du succès attendu.
- [x] 2.5 Stocker les tâches d’import et sérialiser leur exécution ; annuler puis attendre leur arrêt dans async_unload_entry.

## 3. Validation et livraison

- [x] 3.1 Exécuter les tests import/recorder/cycle de vie, puis la suite complète ; vérifier l’absence d’écriture après unload.
- [x] 3.2 Mettre à jour la documentation de l’import, des erreurs, de la compatibilité et du retour arrière ; conserver les identifiants des capteurs.

## Validation — 26 octobre 2026

- **242 tests passent** sur HA 2024.6.4 / Python 3.12.14 et HA 2026.10.4 / Python 3.14.4.
- `tests/unit/test_history_import.py` contient **34 cas** portant sur le véritable importeur, des registries/services natifs et le worker recorder avec SQLite temporaire ; les 17 anciens tests de helpers supprimés ont été remplacés.
- Tests : suppression/insertion/ajustement atomiques, injection d’échec après suppression, double import idempotent, absence/erreur/zéro et bornes DST, refus sans baseline valide ou worker arrêté, compilation live HA après import, deux appels service concurrents, déchargement pendant fetch/INSERT/sauvegarde Store, import direct successif et absence de rechargement sur consommation du flag.
- Ruff et `git diff --check` passent ; les tests interdisent les sockets externes.
- L’import automatique initial peut être refusé sans mutation avant les premières statistiques live. La reprise manuelle et les limites de couverture sont documentées dans [docs/08-safe-energy-history-import.md](../../../../docs/08-safe-energy-history-import.md).
- Aucun changement d’identifiant, de version de configuration ou de clé de stockage. Aucune opération vers un compte Intuis réel.
