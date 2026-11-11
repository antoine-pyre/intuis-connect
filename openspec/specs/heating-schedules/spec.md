# heating-schedules Specification

## Purpose
TBD - created by archiving change correct-schedule-mutations. Update Purpose after archive.
## Requirements
### Requirement: Remplacement d’un intervalle hebdomadaire

L’intégration SHALL appliquer la zone demandée à la totalité de l’intervalle semi-ouvert [début, fin), restaurer la zone initiale à la fin et préserver le planning en dehors de cet intervalle.

#### Scenario: Transitions internes
- **WHEN** Eco est demandé lundi de 07:00 à 11:00 et une transition existe à 08:00
- **THEN** Eco reste actif de 07:00 à 11:00 et la transition de 08:00 disparaît

#### Scenario: Passage de semaine
- **WHEN** une plage débute vendredi soir et se termine lundi matin
- **THEN** la zone s’applique continûment à travers dimanche/minuit et les portions hors plage sont conservées

#### Scenario: Fin à minuit
- **WHEN** une plage du dimanche se termine à 00:00 en fin de journée
- **THEN** la borne est normalisée au début de semaine sans créer une transition hors des offsets valides

### Requirement: Précision des températures

L’intégration SHALL conserver les températures acceptées au pas de 0,5 °C dans la requête cloud et l’état local confirmé.

#### Scenario: Deux points d’entrée
- **WHEN** une température de 19,5 °C est demandée par service ou entité number
- **THEN** la requête contient 19,5 et l’état confirmé conserve cette valeur

### Requirement: Mutation confirmée

L’intégration MUST préserver le planning local confirmé si une modification cloud échoue.

#### Scenario: Échec API
- **WHEN** une modification de plage ou température échoue
- **THEN** l’ancien planning et ses températures restent visibles et l’erreur remonte à l’appelant

