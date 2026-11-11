# heating-overrides Specification

## Purpose
TBD - created by archiving change reconcile-heating-overrides. Update Purpose after archive.
## Requirements
### Requirement: Partage des dérogations nouvellement créées

L’intégration SHALL traiter une dérogation créée après un démarrage avec un stockage vide comme une dérogation chargée depuis le stockage.

#### Scenario: Premier démarrage
- **WHEN** une température manuelle est demandée après un démarrage sans dérogation
- **THEN** la dérogation est visible au prochain rafraîchissement, persistée et prolongée en mode indéfini

#### Scenario: Expiration normale
- **WHEN** une dérogation expire avec le mode indéfini désactivé
- **THEN** elle est retirée de l’état partagé et du stockage

### Requirement: Échec de commande et redémarrage

L’intégration SHALL conserver uniquement les intentions confirmées et préserver les dérogations valides à travers les rechargements.

#### Scenario: Commande refusée
- **WHEN** une commande de chauffage échoue
- **THEN** aucune nouvelle dérogation ni état persistant de succès n’est créé

#### Scenario: Rechargement
- **WHEN** une entrée contenant des dérogations actives est rechargée
- **THEN** les dérogations actives restent traitées selon leurs options et aucune ancienne minuterie ne continue à agir

