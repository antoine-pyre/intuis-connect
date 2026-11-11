# Spec Delta

## Purpose

Import et remplacement fiables des statistiques énergétiques. Cette spécification définit le comportement attendu et vérifiable pour Intuis Connect.

## ADDED Requirements

### Requirement: Préservation des données lors d’un échec

L’intégration SHALL préserver les statistiques existantes si la récupération, la validation ou le remplacement de l’historique échoue ; elle MUST préserver les données hors de la période remplacée.

#### Scenario: API indisponible
- **WHEN** une récupération échoue ou renvoie une réponse vide non validée
- **THEN** aucune statistique existante n’est supprimée et le résultat expose un échec exploitable

#### Scenario: Échec pendant le remplacement
- **WHEN** l’écriture échoue après le début du remplacement
- **THEN** les anciennes statistiques restent disponibles ou sont restaurées avant que l’opération soit déclarée terminée

#### Scenario: Premières statistiques live absentes
- **WHEN** un import est demandé sans métadonnées compatibles ou sans baseline short-term live valide après la période à remplacer
- **THEN** l’import est refusé sans mutation avec un message invitant à attendre les premières statistiques live puis à relancer le service

### Requirement: Réimport cohérent et idempotent

L’intégration SHALL importer une série validée dans l’ordre chronologique sans doublons et conserver une somme cumulée cohérente avec les statistiques antérieures et postérieures.

#### Scenario: Réimport identique
- **WHEN** la même période est importée deux fois
- **THEN** les statistiques et sommes finales sont identiques après les deux imports

#### Scenario: Période partiellement renseignée
- **WHEN** la série présente des jours nuls, absents ou des bornes de journée locales
- **THEN** les valeurs nulles valides restent distinctes des absences et seules les périodes validées peuvent être remplacées

### Requirement: Cycle de vie et résultat exacts

L’intégration SHALL exposer un résultat distinguant succès, échec, annulation et limitation API, et MUST arrêter les écritures d’un import avant la fin du déchargement de son entrée.

#### Scenario: Déchargement en cours d’import
- **WHEN** une entrée est déchargée pendant la récupération ou entre deux pièces
- **THEN** le traitement est arrêté et aucune nouvelle écriture ne survient après le déchargement

#### Scenario: Échec partiel
- **WHEN** une pièce échoue et une autre réussit
- **THEN** le résultat indique les succès et erreurs et ne présente pas l’ensemble comme un succès complet
