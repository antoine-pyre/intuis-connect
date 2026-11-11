# multi-home-services Specification

## Purpose
TBD - created by archiving change fix-multi-home-service-contracts. Update Purpose after archive.
## Requirements
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

Les services SHALL conserver leur comportement sans home_id : première entrée éligible pour les mutations de planning, toutes les entrées pour refresh et import sans filtre de pièce, avec avertissement lors d’un choix implicite ambigu.

#### Scenario: Automatisation existante
- **WHEN** une automatisation sans home_id est exécutée
- **THEN** les noms et champs des services restent compatibles et le défaut documenté est conservé

#### Scenario: Import filtré sans domicile explicite
- **WHEN** un import sans home_id fournit un room_name non vide
- **THEN** seuls les domiciles contenant cette pièce sont ciblés et aucun match produit une erreur avant création d’une tâche

### Requirement: Descriptions sans écriture dans le composant

L’intégration SHALL fournir des descriptions de services cohérentes et MUST fonctionner lorsque ses fichiers installés sont en lecture seule.

#### Scenario: Installation en lecture seule
- **WHEN** l’intégration démarre puis rafraîchit les plannings
- **THEN** les services restent utilisables sans tentative d’écriture dans services.yaml

### Requirement: Cycle de vie des services de domaine

Les services SHALL rester disponibles tant qu’une entrée éligible reste chargée et MUST être désenregistrés après le dernier déchargement réussi. Les acquittements tardifs MUST éviter de rafraîchir le coordinateur d’une entrée retirée.

#### Scenario: Retrait du premier puis dernier domicile
- **WHEN** la première entrée est retirée alors qu’une autre demeure, puis la dernière entrée est retirée
- **THEN** les services fonctionnent encore pour la seconde entrée avant d’être retirés avec la dernière

#### Scenario: Déchargement refusé
- **WHEN** le déchargement des plateformes échoue
- **THEN** les services demeurent enregistrés et utilisables pour les entrées encore chargées

