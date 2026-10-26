# Design

## Context

intuis_data.py, climate.py, __init__.py, tests/conftest.py, tests/unit/test_overrides.py, tests/unit/test_climate.py.

La motivation et les contrats sont décrits dans proposal.md et specs/. Les dépendances sont précisées dans le plan global.

## Goals / Non-Goals

**Goals:** rendre les contrats spécifiés testables et fiables en préservant les identifiants et les données existantes.

**Non-Goals:** ajouter de nouvelles fonctions produit, modifier les équipements réels ou lancer un import cloud pendant la planification.

## Decisions

1. Corriger immédiatement le fallback de dictionnaire, y compris dans les fixtures qui reproduisent le même défaut. Garder le conteneur partagé stable à travers les commandes et mises à jour.

2. Centraliser création, suppression et sauvegarde des intentions dans une interface commune ; préserver le format de stockage existant ou fournir une migration explicite.

3. Séparer l’intention persistée de la commande en attente. Borner l’optimisme à une durée explicite, le lever sur confirmation ou expiration et traiter le mode cloud comme référence pour l’affichage confirmé.

4. Enregistrer les fonctions d’annulation des minuteries, remplacer les anciens callbacks d’une pièce et les nettoyer au retrait des entités.

## Risks / Trade-offs

Le cloud peut présenter un léger retard : les tests doivent couvrir confirmation retardée, expiration et rafraîchissement échoué sans figer l’affichage. La prolongation indéfinie reste une intention explicite configurée par l’utilisateur.

## Migration Plan

1. Établir les tests de régression sur les contrats existants et le cas défaillant.
2. Implémenter le changement avec les tests du lot ; maintenir les identifiants publics et formats persistés, ou fournir une migration explicitement testée.
3. Exécuter les contrôles ciblés puis la suite et la matrice supportée.
4. Documenter les changements de comportement et les limites de compatibilité.
5. En cas de régression, revenir à la version de code précédente ; ne jamais supprimer les données utilisateur pour effectuer ce retour. Une transaction recorder déjà confirmée ne s’annule pas par simple rollback du code.

## Décisions d’implémentation — 26 octobre 2026

- `OverrideManager` conserve l’identité du dictionnaire et le format de stockage.
  Les locks par pièce sérialisent commandes/reapply ; la suppression d’une
  expiration vérifie l’identité du snapshot pour préserver les commandes récentes.
- L’état optimiste est distinct de l’intention : `PendingCommand`, délai monotone
  de 120 secondes et minuterie locale indépendante de la fin du preset.
  `assumed_state` est vrai uniquement pendant l’attente.
- La confirmation passe par le callback de DataUpdateCoordinator. Modes auto/home
  équivalents, consigne et boost observés servent à confirmer. Pour les presets
  encodés manual+temp, une expiration fournie doit correspondre à 60 secondes près.
  Les limites de cette observation sans expiration sont documentées.
- L’intention d’une commande acceptée et l’état en attente sont publiés avant la
  sauvegarde : une erreur disque remonte sans faire croire que l’envoi a échoué.
  La closure de persistance du setup capture une copie profonde du dictionnaire.
- Les timers d’optimisme et de fin sont remplacés par commande, la fin est
  replanifiée après prolongation, et les deux sont annulés au retrait HA. Un
  acquittement réseau tardif ne réactive pas l’entité retirée.
- Tests sur véritables mapping, coordinateur et Store ; retrait par `async_remove`
  afin de vérifier aussi le désabonnement du listener du coordinateur.
