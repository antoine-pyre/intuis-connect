# Spec Delta

## ADDED Requirements

### Requirement: Préservation du contrat existant

L’intégration MUST préserver les identifiants, états journaliers, statistiques et automatisations existants ; les nouvelles séries SHALL avoir des identifiants stables distincts.

#### Scenario: Activation facultative
- **WHEN** la collecte horaire est activée puis désactivée
- **THEN** le capteur journalier conserve son ID, son sens et son suivi ; les anciennes statistiques ne sont pas effacées

### Requirement: Heures closes et séries valides

L’import horaire SHALL ne traiter que des heures closes et consolidables ; il MUST distinguer zéro, absence et erreur et MUST NOT additionner une répétition du même point.

#### Scenario: Chevauchement de requêtes
- **WHEN** deux chunks retournent le même point de 500 Wh
- **THEN** une seule consommation de 500 Wh est retenue ; une contradiction est refusée avant mutation

### Requirement: Continuité et acquittement

Les écritures SHALL être idempotentes et confirmées après transaction, avec continuité des sommes et rollback sur échec.

#### Scenario: Échec d’insertion
- **WHEN** une transaction échoue après validation
- **THEN** l’ancienne série est conservée et aucune ancre de progression ne prétend que le remplacement a réussi

### Requirement: Isolation et reprise

L’updater SHALL isoler chaque domicile et reprendre les heures manquantes dans la fenêtre de rattrapage bornée.

#### Scenario: Deux domiciles et arrêt
- **WHEN** un domicile importe pendant que l’autre se met à jour puis le premier est déchargé
- **THEN** le second continue et le premier ne peut plus écrire après la fin de son unload

### Requirement: Agrégat horaire du domicile

L’intégration SHALL fournir le cumul du domicile dans une série distincte de l’agrégat journalier existant et MUST NOT présenter un total partiel comme complet.

#### Scenario: Pièce absente
- **WHEN** une pièce ne dispose pas de données confirmées pour une heure du total
- **THEN** l’incomplétude est signalée et le total ne remplace pas la dernière valeur complète par un cumul partiel
