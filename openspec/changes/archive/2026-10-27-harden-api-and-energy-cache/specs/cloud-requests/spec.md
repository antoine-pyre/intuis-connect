# Spec Delta

## Purpose

Requêtes cloud et réauthentification conservant leur destination. Cette spécification définit le comportement attendu et vérifiable pour Intuis Connect.

## ADDED Requirements

### Requirement: Nouvelle tentative fidèle

Le client SHALL conserver méthode, URL complète avec query, corps, en-têtes spécifiques et timeout lors d’une nouvelle tentative après 401 ; seul le jeton d’autorisation SHALL être actualisé.

#### Scenario: Endpoint énergie
- **WHEN** un appel vers le serveur énergie reçoit 401 puis le renouvellement réussit
- **THEN** la seconde requête vise exactement la même URL avec le même payload et timeout et le nouveau jeton

#### Scenario: Authentification toujours invalide
- **WHEN** la requête rejouée reçoit encore 401
- **THEN** l’opération échoue de manière explicite sans boucle de renouvellement
