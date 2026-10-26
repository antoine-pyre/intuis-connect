# Spec Delta

## Purpose

Services adressables par domicile et validés sur les données actuelles. Cette spécification définit le comportement attendu et vérifiable pour Intuis Connect.

## ADDED Requirements

### Requirement: Ciblage accepté et isolé

Les services de changement de planning, d’édition de plage, de température, de rafraîchissement et d’import SHALL accepter home_id et MUST limiter leur action au domicile désigné.

#### Scenario: Deux domiciles
- **WHEN** un service valide est appelé avec l’identifiant du second domicile
- **THEN** le schéma accepte l’appel et seule son API reçoit la commande

#### Scenario: Domicile inconnu
- **WHEN** home_id ne correspond à aucune entrée chargée
- **THEN** une erreur explicite est retournée et aucune commande n’est envoyée

### Requirement: Données courantes disponibles

Les services SHALL accepter les noms valides du domicile ciblé après ajout, rechargement ou rafraîchissement et MUST rejeter les références invalides avant toute commande.

#### Scenario: Nouveau planning
- **WHEN** un planning est ajouté au second domicile puis les données sont rafraîchies
- **THEN** le service peut le cibler sans redémarrage de HA

#### Scenario: Noms identiques
- **WHEN** deux domiciles ont un planning de même nom et home_id est fourni
- **THEN** le planning du domicile ciblé est le seul modifié

### Requirement: Compatibilité des appels sans domicile

Les services SHALL conserver leur comportement sans home_id : première entrée éligible pour les mutations de planning, toutes les entrées pour refresh et import, avec avertissement lors d’un choix implicite ambigu.

#### Scenario: Automatisation existante
- **WHEN** une automatisation sans home_id est exécutée
- **THEN** les noms et champs des services restent compatibles et le défaut documenté est conservé

### Requirement: Descriptions sans écriture dans le composant

L’intégration SHALL fournir des descriptions de services cohérentes et MUST fonctionner lorsque ses fichiers installés sont en lecture seule.

#### Scenario: Installation en lecture seule
- **WHEN** l’intégration démarre puis rafraîchit les plannings
- **THEN** les services restent utilisables sans tentative d’écriture dans services.yaml
