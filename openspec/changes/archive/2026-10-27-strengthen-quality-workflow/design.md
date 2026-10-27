# Design

## Context

requirements_dev.txt, pytest.ini, .github/workflows/tests.yml, .devcontainer/devcontainer.json, tests/conftest.py, tests/PLAN.md, services.py, number.py, intuis_data.py, docs/, README.md ; configuration Ruff et modules métier à créer.

La motivation et les contrats sont décrits dans proposal.md et specs/. Les dépendances sont précisées dans le plan global.

## Goals / Non-Goals

**Goals:** rendre les contrats spécifiés testables et fiables en préservant les identifiants et les données existantes.

**Non-Goals:** ajouter de nouvelles fonctions produit, modifier les équipements réels ou lancer un import cloud pendant la planification.

## Decisions

1. Procéder en deux étapes : socle de validation avant les correctifs, refactoring structurel après leurs régressions. Ne pas conditionner les P1 à une réécriture globale.

2. Choisir et fixer des versions Python/HA réellement compatibles ; vérifier le minimum HA 2024.6 annoncé, maintenir une matrice minimum/courante avec contraintes versionnées, et mettre à jour README/hacs.json si une hausse du minimum est nécessaire et justifiée.

3. Définir un jeu Ruff explicite et traiter les défauts existants par lots sans masquer globalement les règles. Utiliser des dépendances/contraintes reproductibles par environnement, sans pinner les dépendances runtime gérées par HA au hasard.

4. Extraire résolution des cibles, mutations de planning et coordination des dérogations vers des modules métier ; laisser dans services.py schémas et orchestration. Éviter la duplication avec number.py et climate.py.

5. Remplacer les tests qui affirment seulement qu’un mock a été appelé par des tests du handler enregistré ; limiter les mocks aux frontières transport, horloge et stockage. Les fixtures doivent respecter les vrais contrats.

## Risks / Trade-offs

Une hausse de version minimale HA est un changement de compatibilité : d’abord mesurer la compatibilité réelle, maintenir le minimum annoncé si faisable, sinon documenter la nouvelle limite et les raisons avant livraison. Ne pas interpréter le nombre de tests comme un taux de couverture.

## Migration Plan

1. Établir les tests de régression sur les contrats existants et le cas défaillant.
2. Implémenter le changement avec les tests du lot ; maintenir les identifiants publics et formats persistés, ou fournir une migration explicitement testée.
3. Exécuter les contrôles ciblés puis la suite et la matrice supportée.
4. Documenter les changements de comportement et les limites de compatibilité.
5. En cas de régression, revenir à la version de code précédente ; ne jamais supprimer les données utilisateur pour effectuer ce retour. Une transaction recorder déjà confirmée ne s’annule pas par simple rollback du code.

## Réalisation et limites de la consolidation

Les extractions prévues ont été réalisées dans les lots fonctionnels :
`service_targets.py`, `schedule_mutations.py` et `overrides.py` remplacent la
résolution cachée, les payloads dupliqués et les sources d’intentions séparées.
La consolidation ne rajoute pas de couche générique au-dessus de ces modules.

Les tests sans appel produit ont été supprimés uniquement après remplacement
par les suites natives des services, plannings et compatibilité. Un parcours
setup → unload → setup utilise les factories d’entités de production et le
registry pour comparer les identifiants effectivement calculés et persistés.
La migration V2 native conserve identité/données même lors d’une erreur de
réseau, d’une limitation API ou d’une réponse malformée ; elle ne masque plus
les erreurs de programmation non prévues. Les exceptions larges de terminaison
du worker/import sont conservées pour garantir rollback, statut et drainage.

Le format stocké des dérogations est documenté par un TypedDict permissif aux
anciennes entrées partielles, sans conversion à l’exécution. Les annotations et
valeurs par défaut documentées sont alignées sur les objets existants. Aucun
minimum HA/HACS n’est relevé ; la matrice vérifie le minimum annoncé et une
version récente précise. La validation locale ne remplace pas l’exécution de
CI distante ni un test sur de vrais radiateurs.
