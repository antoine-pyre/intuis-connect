# energy-measurements Specification

## Purpose
TBD - created by archiving change harden-api-and-energy-cache. Update Purpose after archive.
## Requirements
### Requirement: Zéro distinct d’une indisponibilité

L’intégration SHALL distinguer une consommation valide de zéro d’une erreur ou d’une absence de mesure et MUST éviter d’enregistrer une erreur comme un zéro confirmé.

#### Scenario: Pièce en échec
- **WHEN** une pièce échoue alors qu’une autre renvoie une mesure valide
- **THEN** la mesure valide est exploitable et la pièce en échec ne reçoit pas un faux zéro

#### Scenario: Zéro valide
- **WHEN** le cloud renvoie une mesure explicitement valide de zéro
- **THEN** zéro est accepté et peut être mis en cache

### Requirement: Nouvelle tentative après échec

L’intégration SHALL retenter une mesure en échec au prochain cycle éligible sans attendre l’invalidation quotidienne des mesures réussies.

#### Scenario: Panne temporaire
- **WHEN** la récupération échoue puis réussit au cycle suivant
- **THEN** la consommation correcte est publiée le même jour sans réinitialisation manuelle

#### Scenario: Première mesure indisponible
- **WHEN** aucune mesure valide n’existe encore pour une pièce
- **THEN** le capteur expose une absence de donnée plutôt qu’une consommation nulle fabriquée

