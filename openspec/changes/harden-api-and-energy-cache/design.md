# Design

## Context

intuis_api/api.py, intuis_data.py, sensor.py ; tests client HTTP et cache à créer.

La motivation et les contrats sont décrits dans proposal.md et specs/. Les dépendances sont précisées dans le plan global.

## Goals / Non-Goals

**Goals:** rendre les contrats spécifiés testables et fiables en préservant les identifiants et les données existantes.

**Non-Goals:** ajouter de nouvelles fonctions produit, modifier les équipements réels ou lancer un import cloud pendant la planification.

## Decisions

1. Préserver les arguments d’origine de la requête dans une structure dédiée ou une boucle de retry, plutôt que réutiliser des kwargs déjà consommés. Garder une seule réauthentification par opération.

2. Retourner des erreurs typées ou un résultat structuré par pièce ; ne plus convertir les erreurs de parsing/HTTP en 0.0. Faire migrer ensemble les appelants et leurs annotations.

3. Suivre succès, jour et disponibilité par pièce. Conserver la dernière valeur valide pendant une panne, avec son statut de fraîcheur ; ne jamais avancer la date de succès d’une pièce en échec.

4. Tester les réponses via un transport HTTP simulé fidèle à aiohttp. Ne pas conclure à un défaut de bibliothèque sur la seule base d’un MagicMock simplifié.

## Risks / Trade-offs

Changer le contrat interne des mesures affecte tous les appelants : les inventorier avant modification. Une valeur conservée doit rester identifiable comme ancienne pour éviter de présenter une panne comme une mesure fraîche.

## Migration Plan

1. Établir les tests de régression sur les contrats existants et le cas défaillant.
2. Implémenter le changement avec les tests du lot ; maintenir les identifiants publics et formats persistés, ou fournir une migration explicitement testée.
3. Exécuter les contrôles ciblés puis la suite et la matrice supportée.
4. Documenter les changements de comportement et les limites de compatibilité.
5. En cas de régression, revenir à la version de code précédente ; ne jamais supprimer les données utilisateur pour effectuer ce retour. Une transaction recorder déjà confirmée ne s’annule pas par simple rollback du code.
