# Design

## Context

timetable.py, services.py, number.py, entity/intuis_schedule.py, tests/unit/test_schedule_helpers.py, tests/unit/test_services.py ; tests number à créer.

La motivation et les contrats sont décrits dans proposal.md et specs/. Les dépendances sont précisées dans le plan global.

## Goals / Non-Goals

**Goals:** rendre les contrats spécifiés testables et fiables en préservant les identifiants et les données existantes.

**Non-Goals:** ajouter de nouvelles fonctions produit, modifier les équipements réels ou lancer un import cloud pendant la planification.

## Decisions

1. Extraire une transformation pure d’intervalle cyclique sur 10080 minutes. Capturer la zone d’origine de fin avant mutation, retirer toutes les transitions internes, insérer les bornes et normaliser tri/doublons.

2. Définir l’intervalle comme semi-ouvert ; conserver le sens actuel de fin à 00:00 le même jour, normaliser 10080 vers 0 et rejeter les intervalles ambigus ou invalides.

3. Utiliser des valeurs décimales dans les modèles et sérialisations, valider la plage et le pas sans troncature silencieuse.

4. Construire le payload sur une copie ; publier l’état local uniquement après succès. Faire utiliser le même chemin métier aux services et entités number pour éviter leur divergence.

## Risks / Trade-offs

Les limites cycliques et les plannings sans transition à zéro exigent des tests de couverture de toute la semaine. Les mises à jour concurrentes d’un planning doivent être sérialisées pour éviter les écrasements locaux.

## Migration Plan

1. Établir les tests de régression sur les contrats existants et le cas défaillant.
2. Implémenter le changement avec les tests du lot ; maintenir les identifiants publics et formats persistés, ou fournir une migration explicitement testée.
3. Exécuter les contrôles ciblés puis la suite et la matrice supportée.
4. Documenter les changements de comportement et les limites de compatibilité.
5. En cas de régression, revenir à la version de code précédente ; ne jamais supprimer les données utilisateur pour effectuer ce retour. Une transaction recorder déjà confirmée ne s’annule pas par simple rollback du code.


## Décisions d’implémentation — 26 octobre 2026

- `schedule_mutations.py` mutualise les deux opérations et la sérialisation du payload.
  La map de verrous est déclarée et typée dans `IntuisAPI` ; elle est partagée par
  services et number, avec résolution des modèles après acquisition puis avant publication.
- La copie reste privée jusqu’à confirmation du cloud. Une erreur API ou une
  valeur invalide ne modifie ni le planning ni le cache confirmé des entités.
- `schedule_slot_offsets` valide les paramètres du service, conserve `day` en alias
  et la convention de fin à minuit le même jour. Les secondes non nulles et les
  intervalles ambigus sont refusés explicitement.
- Les 42 régressions nouvelles passent par les vrais handlers enregistrés ou le
  setter de l’entité number ; l’invariance est vérifiée minute par minute sur une
  semaine complète, et une course mixte inclut un remplacement du modèle pendant l’attente API.
- Les verrous ne prétendent pas coordonner les modifications provenant d’autres
  clients Intuis : aucune version/ETag de planning n’est fournie au contrat utilisé.
