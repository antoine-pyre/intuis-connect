# Spec Delta

## Purpose

État climate réconcilié avec le retour des équipements. Cette spécification définit le comportement attendu et vérifiable pour Intuis Connect.

## ADDED Requirements

### Requirement: Retour à l’état observé

L’intégration SHALL réconcilier le mode HVAC et le preset affichés avec les mises à jour cloud et MUST borner dans le temps tout affichage optimiste.

#### Scenario: Fin de boost
- **WHEN** un boost demandé depuis HA expire et un rafraîchissement confirme le mode auto
- **THEN** le mode et le preset affichent le retour au planning

#### Scenario: Changement externe
- **WHEN** l’utilisateur modifie le mode dans l’application Intuis après une commande HA
- **THEN** le prochain retour cloud confirmé actualise le mode affiché

#### Scenario: Confirmation retardée
- **WHEN** le cloud ne confirme pas la commande ou le rafraîchissement échoue
- **THEN** l’état optimiste n’est pas présenté indéfiniment comme un état confirmé
