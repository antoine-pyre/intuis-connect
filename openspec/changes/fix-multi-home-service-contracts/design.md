# Design

## Context

services.py, services.yaml, __init__.py, translations/en.json, translations/fr.json, tests/unit/test_multi_home.py, tests/unit/test_services.py.

La motivation et les contrats sont décrits dans proposal.md et specs/. Les dépendances sont précisées dans le plan global.

## Goals / Non-Goals

**Goals:** rendre les contrats spécifiés testables et fiables en préservant les identifiants et les données existantes.

**Non-Goals:** ajouter de nouvelles fonctions produit, modifier les équipements réels ou lancer un import cloud pendant la planification.

## Decisions

1. Déclarer home_id optionnel dans tous les schémas concernés et centraliser la résolution des entrées ainsi que les erreurs métier.

2. Conserver services.yaml statique. Utiliser des champs texte pour les noms dépendant du domicile et les valider dans le handler sur les données actuelles ; cette solution évite des listes figées et fonctionne sur les versions HA retenues.

3. Documenter les défauts sans cible ; préserver les champs historiques encore pris en charge, notamment day, et aligner les descriptions UI sur start_day/end_day réellement acceptés.

4. Enregistrer les services au niveau domaine, nettoyer les inscriptions à la dernière entrée déchargée et éviter les closures dépendant uniquement de la première entrée.

## Risks / Trade-offs

Les listes dynamiques deviennent des saisies de noms validées à l’exécution : documenter ce changement d’interface et fournir des exemples multi-domicile. Conserver la compatibilité des automatisations valides existantes.

## Migration Plan

1. Établir les tests de régression sur les contrats existants et le cas défaillant.
2. Implémenter le changement avec les tests du lot ; maintenir les identifiants publics et formats persistés, ou fournir une migration explicitement testée.
3. Exécuter les contrôles ciblés puis la suite et la matrice supportée.
4. Documenter les changements de comportement et les limites de compatibilité.
5. En cas de régression, revenir à la version de code précédente ; ne jamais supprimer les données utilisateur pour effectuer ce retour. Une transaction recorder déjà confirmée ne s’annule pas par simple rollback du code.
