# Spec Delta

## ADDED Requirements

### Requirement: Distribution et authentification

L’intégration SHALL servir l’éditeur embarqué à l’URL prévue sans exposer de données ni commandes HA sans authentification.

#### Scenario: Accès sans session
- **WHEN** un navigateur non authentifié ouvre la coque HTML
- **THEN** aucune donnée du domicile ni commande cloud n’est accessible sans authentification HA

### Requirement: Édition et sauvegarde

L’éditeur SHALL proposer les fonctions de planning source et ne déclarer la sauvegarde réussie qu’après les réponses confirmées.

#### Scenario: Échec partiel
- **WHEN** une température échoue après une autre modification confirmée
- **THEN** les résultats partiels sont visibles et les modifications restantes ne sont pas marquées comme enregistrées

### Requirement: Rendu sûr et session

L’éditeur MUST afficher les valeurs cloud comme du texte et MUST NOT persister un token durable sans choix explicite.

#### Scenario: Nom de zone contenant du HTML
- **WHEN** le cloud fournit une zone dont le nom contient une balise
- **THEN** le nom est affiché littéralement sans exécution et aucun token n’est présent dans l’URL

### Requirement: Crédit et compatibilité

L’éditeur SHALL rendre le crédit source consultable et MUST préserver les automatisations existantes et la compatibilité HA annoncée.

#### Scenario: Mise à jour de l’intégration
- **WHEN** HACS distribue une nouvelle version du planning
- **THEN** l’asset actualisé est servi avec cache cohérent et le crédit source reste accessible
