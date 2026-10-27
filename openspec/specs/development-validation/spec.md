# development-validation Specification

## Purpose
TBD - created by archiving change strengthen-quality-workflow. Update Purpose after archive.
## Requirements
### Requirement: Validation automatisée des contributions

Le dépôt SHALL fournir des commandes reproductibles pour exécuter les tests hors ligne et les contrôles de qualité et SHALL faire échouer les checks CI configurés lorsqu’un contrôle échoue.

#### Scenario: Régression introduite
- **WHEN** une contribution casse un comportement couvert ou une règle de lint active
- **THEN** le check correspondant échoue et identifie le défaut

#### Scenario: Nouvel environnement
- **WHEN** un développeur prépare l’environnement documenté
- **THEN** les dépendances, versions Python/HA et commandes permettent de lancer les mêmes contrôles qu’en CI

### Requirement: Régressions aux frontières publiques

La suite de tests SHALL exercer les handlers et le code de production à travers leurs points d’entrée pour les contrats critiques de l’intégration, sans accès au cloud réel.

#### Scenario: Champ rejeté par le schéma
- **WHEN** un paramètre documenté n’est plus accepté par un service
- **THEN** un test appelant le service réellement enregistré détecte la régression

#### Scenario: Données persistées
- **WHEN** un changement affecte dérogations ou statistiques
- **THEN** des tests de rechargement ou recorder avec stockage temporaire détectent la perte de données

