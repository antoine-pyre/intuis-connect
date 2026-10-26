# Spec Delta

## ADDED Requirements

### Requirement: Attribution traçable

Chaque adaptation SHALL conserver un lien vers la PR source, son auteur vérifié et sa révision ; le registre MUST distinguer le statut réel de livraison.

#### Scenario: Adaptation de code
- **WHEN** une fonction inspirée de #22 est livrée sous un nouveau commit
- **THEN** le registre, la description et le commit citent TheFab21 et la source sans annoncer une fusion de #22

### Requirement: Identités et notices

Le projet MUST conserver les notices présentes dans les sources reprises et MUST NOT inventer une identité de coauteur.

#### Scenario: Auteur sans adresse vérifiée
- **WHEN** seul le login GitHub d’un contributeur est connu
- **THEN** le crédit utilise ce login et un lien sans construire une adresse de messagerie

### Requirement: Crédit historique

La documentation SHALL conserver le crédit du créateur et des contributions antérieures indépendamment du statut des PRs nouvelles.

#### Scenario: Fonction déjà intégrée
- **WHEN** une fonction de #11 est déjà présente
- **THEN** chrislek reste crédité et la fonction n’est pas présentée comme nouvellement développée
