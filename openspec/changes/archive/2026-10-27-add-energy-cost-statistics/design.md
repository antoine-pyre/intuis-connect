# Design

## Context

Les coûts, le prix historique et leur recalcul sont absents du projet. Le code proposé par #22 fournit une base fonctionnelle, mais comporte des défauts de configuration, migration et publication.

Socle : `f92e3e4`, 334 tests sur HA 2024.6.4 et 2026.10.4. nouveau cost_stats.py, capteurs coût, config_flow, recorder, services, traductions et tests ; source TheFab21 #22/#24.

## Goals / Non-Goals

**Goals:** Ajouter des coûts par pièce et domicile avec prix fixe ou entité HA et historique explicite. Fournir une série statistique de coût et un capteur d’affichage distincts de l’énergie existante. Ajouter un recalcul ciblé, idempotent et non destructif.

**Non-Goals:** fusion globale des anciennes branches, modification d’équipements réels pendant les tests, modification implicite des IDs ou suppression de données utilisateur.

## Decisions

1. Fonction opt-in, indépendante des commandes de chauffage ; requiert les séries kWh validées du lot horaire. La désactivation conserve l’historique. Le prix fixe initial peut proposer 0,25 mais n’est jamais appliqué sans configuration explicite.

2. Tarif fixe : la valeur configurée s’applique à la période explicitement demandée au recalcul. Tarif par entité : prix historique au début de chaque heure, avec unité/devise validées ; documenter cette approximation quand le prix varie à l’intérieur d’une heure.

3. Ne pas appliquer rétroactivement le prix courant aux heures sans historique. En cas de trou de prix, refuser la période affectée avec une erreur exploitable et préserver ses anciennes statistiques ; pas de fallback silencieux au prix fixe.

4. Utiliser des séries externes de coût distinctes, source intuis_connect, IDs fondés sur domicile/pièce. Le capteur cumulatif d’affichage ne génère pas une seconde écriture sur la même série. Une seule devise compatible est autorisée par série ; un changement de devise exige un traitement explicite.

5. Les sélecteurs sont vérifiés sur les deux versions HA, sans pas numérique rejeté ni liste de sélection manquante. Les services restent statiques, traduits et compatibles home_id/room_name.

6. La migration d’anciennes installations communautaires n’est pas présumée nécessaire pour les utilisateurs du dépôt actuel. Inventorier les anciens IDs sans suppression ; toute reprise proposée est facultative, bornée aux entités de ce domaine, vérifiée et collision-safe.

7. Les coûts sont recalculés depuis les kWh confirmés et prix valides, sous transaction par pièce ; publier après acquittement. Utiliser des méthodes publiques nommées et tester le service réel jusqu’à sa réponse.

## Risks / Trade-offs

Les garanties recorder, les sélecteurs et la vue HTTP doivent être validés sur les deux versions HA. La compatibilité cloud réelle et le comportement matériel ne sont pas prouvés par des tests hors ligne. Les changements d’API HA futurs exigent une nouvelle validation. Les modifications externes simultanées de planning ne disposent pas d’un compare-and-swap cloud.

## Migration Plan

1. Contrat horaire validé dans add-hourly-energy-statistics ; attribution.
2. Vérifier les contrats du socle puis implémenter et tester uniquement le lot.
3. Préserver configuration, identifiants, données et défauts des fonctions existantes ; activation des nouvelles fonctions explicite quand applicable.
4. Vérifier crédits, provenance, documentation et matrice avant livraison.
5. Un retour de code ne supprime pas des statistiques déjà confirmées ; ne jamais supprimer des données pour revenir à une version précédente.
