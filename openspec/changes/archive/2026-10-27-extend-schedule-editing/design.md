# Design

## Context

Le projet ne permet pas encore de remplacer un timetable complet par service, de cibler un planning inactif pour ses créneaux ni de régler ses températures away/hg. Les renommages et données UI des PRs restent aussi utiles.

Socle : `f92e3e4`, 334 tests sur HA 2024.6.4 et 2026.10.4. schedule_mutations.py, service_targets.py, services.py/yaml, number.py, calendar.py, entity/intuis_home_entity.py, timetable.py et traductions/tests ; sources TheFab21 #17/#22/#24.

## Goals / Non-Goals

**Goals:** Étendre set_schedule_slot aux plannings nommés ou identifiés, en conservant le défaut actif. Ajouter sync_schedule pour le timetable complet et les températures absence/hors-gel. Actualiser les libellés de calendrier/number après renommage et enrichir les summaries existants pour l’UI.

**Non-Goals:** fusion globale des anciennes branches, modification d’équipements réels pendant les tests, modification implicite des IDs ou suppression de données utilisateur.

## Decisions

1. Conserver le schéma historique et le planning actif par défaut pour set_schedule_slot ; ajouter schedule_id/schedule_name. Si les deux sont fournis ils doivent désigner le même planning du domicile courant ; ambiguïtés et cibles inconnues sont rejetées avant transport.

2. sync_schedule accepte une liste structurée de transitions ; un JSON texte compatible avec le frontend source peut être accepté après parsing et la même validation. Offsets uniques entiers 0..10079, zones présentes dans le planning, couverture cyclique préservée et limites de taille explicites. Ne pas corriger silencieusement des zones inconnues ou des doublons contradictoires.

3. Mutualiser timetable complet, créneaux, number et températures away/hg sous le verrou existant par planning. Copie du modèle courant, conservation des autres champs, écriture cloud puis publication sur le modèle courant après succès ; pas de duplication d’un ancien handler.

4. away_temp et hg_temp sont optionnels et validés au pas de 0,5 °C, avec bornes 5..25 et 5..15 respectivement. Une mise à jour de température peut conserver le timetable si celui-ci est omis ; un appel ne modifiant aucun champ est rejeté.

5. Conserver les IDs d’entités/devices et leurs noms personnalisés. Noms par défaut relus dynamiquement, mise à jour explicite du registry si nécessaire et tests de renommage après refresh, sans recréer les entités.

6. Enrichir les summaries effectivement instanciés avec home_id/room_names et une semaine à sept jours. Représenter aussi les plages héritées des jours précédents sans réinventer l’héritage du dimanche au lundi. Conserver les anciens attributs et ne pas instancier un second capteur par planning.

7. Descriptions services statiques, erreurs visibles, noms courants, snapshots et unload conservés ; logs utiles sans payload complet systématique ni données personnelles ajoutées.

## Risks / Trade-offs

Les garanties recorder, les sélecteurs et la vue HTTP doivent être validés sur les deux versions HA. La compatibilité cloud réelle et le comportement matériel ne sont pas prouvés par des tests hors ligne. Les changements d’API HA futurs exigent une nouvelle validation. Les modifications externes simultanées de planning ne disposent pas d’un compare-and-swap cloud.

## Migration Plan

1. Socle correct-schedule-mutations et fix-multi-home-service-contracts ; attribution ; indépendant de l’énergie.
2. Vérifier les contrats du socle puis implémenter et tester uniquement le lot.
3. Préserver configuration, identifiants, données et défauts des fonctions existantes ; activation des nouvelles fonctions explicite quand applicable.
4. Vérifier crédits, provenance, documentation et matrice avant livraison.
5. Un retour de code ne supprime pas des statistiques déjà confirmées ; ne jamais supprimer des données pour revenir à une version précédente.
