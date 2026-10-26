# Tasks

Les cases cochées correspondent aux travaux réalisés et vérifiés ; voir docs/pr-integration-progress.md.

## 1. Services et validation

- [x] 1.1 Ajouter les cibles schedule_name/schedule_id avec compatibilité des anciens appels et validation multi-domicile.
- [x] 1.2 Définir puis implémenter le schéma statique sync_schedule, la liste structurée/JSON, les bornes et les champs away/hg.
- [x] 1.3 Etendre le moteur de mutation partagé pour les remplacements complets et températures de planning sans modifier les chemins déjà validés.

## 2. Entités et UI

- [x] 2.1 Actualiser les noms par défaut calendar/device number en conservant IDs et noms personnalisés.
- [x] 2.2 Enrichir les summaries réels avec home_id, room_names et sept jours/plages héritées ; éviter toute nouvelle classe de capteur inutilisée.

## 3. Validation et livraison

- [ ] 3.1 Tester planning inactif, erreurs cloud, ID/nom discordants, semaine cyclique/DST, demi-degrés, payload excessif et concurrence service/number/refresh/unload.
- [ ] 3.2 Exécuter matrice complète et Ruff ; documenter les services et attribuer les apports #17/#22/#24 à TheFab21.
