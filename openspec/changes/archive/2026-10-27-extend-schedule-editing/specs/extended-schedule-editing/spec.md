# Spec Delta

## ADDED Requirements

### Requirement: Ciblage rétrocompatible

set_schedule_slot SHALL utiliser le planning actif en l’absence de cible et SHALL pouvoir cibler un planning inactif sans modifier le planning actif.

#### Scenario: Édition inactive
- **WHEN** un créneau du planning Vacances inactif est demandé avec son ID
- **THEN** seul Vacances est modifié et la sélection active reste intacte

### Requirement: Sauvegarde confirmée

Le service sync_schedule SHALL valider l’ensemble du payload et MUST sérialiser ses mutations avec number et les autres services de planning.

#### Scenario: Éditions concurrentes
- **WHEN** un timetable complet et une température number sont modifiés simultanément
- **THEN** les commandes sont sérialisées et la dernière modification part du dernier modèle confirmé

### Requirement: Températures et non-destruction

Les changements away/hg SHALL préserver tous les champs non modifiés et MUST NOT publier un état non confirmé.

#### Scenario: Échec cloud
- **WHEN** un changement de hg_temp échoue
- **THEN** l’ancienne température et le timetable restent affichés et le service retourne l’erreur

### Requirement: Données UI et identité

Les summaries SHALL fournir les noms de pièces et les sept jours sans modifier les IDs ni les noms personnalisés.

#### Scenario: Renommage et jour hérité
- **WHEN** un planning est renommé et le mardi n’a aucune transition propre
- **THEN** le nom par défaut est actualisé, l’ID reste identique et l’UI peut afficher la zone héritée du lundi
