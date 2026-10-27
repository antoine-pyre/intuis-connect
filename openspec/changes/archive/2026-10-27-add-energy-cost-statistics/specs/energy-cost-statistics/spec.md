# Spec Delta

## ADDED Requirements

### Requirement: Prix explicite

Le calcul SHALL utiliser une convention de prix documentée et MUST NOT substituer silencieusement un prix courant à un historique absent.

#### Scenario: Tarif manquant
- **WHEN** un prix horaire historique manque dans la période demandée
- **THEN** le recalcul concerné échoue clairement et conserve ses statistiques précédentes

### Requirement: Recalcul idempotent

Le service SHALL cibler le domicile demandé, conserver les kWh et confirmer uniquement les écritures de coût acquittées.

#### Scenario: Réexécution
- **WHEN** le même recalcul est demandé deux fois
- **THEN** les coûts et sommes sont identiques et les statistiques énergétiques restent inchangées

### Requirement: Migration et collisions

L’intégration MUST préserver les entités étrangères et les identifiants existants lors de l’ajout des coûts.

#### Scenario: Identifiant déjà occupé
- **WHEN** une autre intégration utilise le nom suggéré du capteur coût
- **THEN** cette entité reste intacte et un ID distinct est obtenu ou une migration explicite est refusée
