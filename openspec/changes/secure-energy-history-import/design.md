# Design

## Context

history_import.py, __init__.py, services.py, tests/unit/test_history_import.py ; adaptateur recorder et tests de cycle de vie à créer.

La motivation et les contrats sont décrits dans proposal.md et specs/. Les dépendances sont précisées dans le plan global.

## Goals / Non-Goals

**Goals:** rendre les contrats spécifiés testables et fiables en préservant les identifiants et les données existantes.

**Non-Goals:** ajouter de nouvelles fonctions produit, modifier les équipements réels ou lancer un import cloud pendant la planification.

## Decisions

1. Découper l’import en récupération, validation/staging, puis remplacement ; valider les timestamps, unités, valeurs finies, doublons et couverture avant mutation. Une série vide ne constitue pas une preuve de consommation nulle.

2. Isoler le recorder dans un adaptateur. Exiger un remplacement atomique dans un job recorder avec transaction, ou refuser explicitement le remplacement destructif si la version HA ne le permet pas. Ne pas enchaîner suppression SQL commitée et import mis en file sans garantie commune.

3. Préserver les baselines et contrôler les bornes horaires et le fuseau du domicile, y compris les changements d’heure. Un réimport du même jeu de données ne doit pas additionner deux fois l’énergie.

4. Conserver une référence à la tâche d’import, sérialiser les imports par entrée, annuler et attendre sa terminaison au déchargement. Publier les statuts seulement après confirmation de l’écriture.

## Risks / Trade-offs

Les API recorder varient selon HA : tester la version minimale retenue et la version courante supportée ; en absence de garantie transactionnelle, retourner une erreur sans suppression. Les transactions volumineuses exigent des bornes par pièce et une validation en mémoire avant leur ouverture.

## Migration Plan

1. Établir les tests de régression sur les contrats existants et le cas défaillant.
2. Implémenter le changement avec les tests du lot ; maintenir les identifiants publics et formats persistés, ou fournir une migration explicitement testée.
3. Exécuter les contrôles ciblés puis la suite et la matrice supportée.
4. Documenter les changements de comportement et les limites de compatibilité.
5. En cas de régression, revenir à la version de code précédente ; ne jamais supprimer les données utilisateur pour effectuer ce retour. Une transaction recorder déjà confirmée ne s’annule pas par simple rollback du code.
