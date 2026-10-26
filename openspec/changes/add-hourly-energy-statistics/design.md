# Design

## Context

Le scale 1hour actuel ne fournit pas un import historique horaire ni un updater de statistiques horaires exactes. #17 et #22 proposent ces capacités mais réécrivent des garanties désormais acquises.

Socle : `f92e3e4`, 334 tests sur HA 2024.6.4 et 2026.10.4. intuis_api/api.py, history_import.py, recorder_import.py, nouveau module hourly_stats.py, __init__.py, config_flow.py, services et traductions, tests recorder/API ; sources #17/#22/#24, TheFab21.

## Goals / Non-Goals

**Goals:** Ajouter un contrat de série horaire strict et des requêtes bornées, avec déduplication des chevauchements. Importer les heures closes dans une série statistique distincte et stable ; ajouter le rattrapage après interruption. Étendre le service d’historique à une granularité explicite, sans changer son défaut quotidien ni les capteurs existants.

**Non-Goals:** fusion globale des anciennes branches, modification d’équipements réels pendant les tests, modification implicite des IDs ou suppression de données utilisateur.

## Decisions

1. Conserver le sens journalier, les IDs, les attributs de fraîcheur et TOTAL_INCREASING des capteurs existants. Les nouvelles statistiques horaires utilisent une identité externe stable fondée sur home_id/room_id et source intuis_connect, distincte des lignes recorder des capteurs journaliers.

2. Valider d’abord, sur les deux versions HA, l’enregistrement et la sélection de cette série externe dans le tableau énergie ainsi que les métadonnées nécessaires. Si le contrat ne fonctionne pas, consigner le blocage et revoir ce design avant de livrer un autre contrat d’identifiants.

3. Désactiver la nouvelle collecte par défaut pour les installations existantes et nouvelles ; option explicite, intervalle initial 120 minutes. Ne pas enlever le contrôle de reset quotidien existant.

4. Ne traiter que les heures entièrement closes depuis au moins 15 minutes ; le cloud peut corriger tardivement les données. Relire les 48 dernières heures et rattraper jusqu’à 7 jours après interruption ; les périodes antérieures passent par l’import manuel, jusqu’à 730 jours.

5. Découper les requêtes selon les limites vérifiées de l’API ; dédupliquer les points identiques par timestamp. Des doublons contradictoires, trous, valeurs négatives/non finies ou erreurs cloud refusent la période concernée avant écriture, sans les transformer en zéro.

6. Etendre le staging et l’adaptateur transactionnel avec un chemin externe séparé : validation, remplacement atomique par pièce, recomposition des sommes depuis les bornes existantes, acquittement après commit et drain au unload. Aucun état auxiliaire stocké ne remplace la vérité recorder.

7. Préserver days/home_id/room_name et le défaut quotidien du service ; ajouter granularity avec les valeurs canoniques daily/hourly, en acceptant les alias 1day/1hour montrés dans la documentation source. Pas de bouton clear_existing destructif : le remplacement est validé et atomique.

8. Coordonner import manuel et updater par domicile/pièce, isoler options et disponibilité par entrée, publier les ancres uniquement après acquittement. Sémantique DST : timestamps UTC uniques, journées locales de 23/25 heures, reprise idempotente.

9. Fournir également un cumul horaire de domicile dans une série et un affichage distincts de l’agrégat journalier actuel. Calculer uniquement à partir des pièces confirmées sur les mêmes heures ; signaler l’incomplétude et conserver la dernière valeur complète. Documenter de sélectionner soit le total domicile, soit ses pièces dans le tableau énergie pour éviter un double comptage de configuration.

## Risks / Trade-offs

Les garanties recorder, les sélecteurs et la vue HTTP doivent être validés sur les deux versions HA. La compatibilité cloud réelle et le comportement matériel ne sont pas prouvés par des tests hors ligne. Les changements d’API HA futurs exigent une nouvelle validation. Les modifications externes simultanées de planning ne disposent pas d’un compare-and-swap cloud.

## Migration Plan

1. Socle local f92e3e4 et attribution ; indépendant des services de planning.
2. Vérifier les contrats du socle puis implémenter et tester uniquement le lot.
3. Préserver configuration, identifiants, données et défauts des fonctions existantes ; activation des nouvelles fonctions explicite quand applicable.
4. Vérifier crédits, provenance, documentation et matrice avant livraison.
5. Un retour de code ne supprime pas des statistiques déjà confirmées ; ne jamais supprimer des données pour revenir à une version précédente.
