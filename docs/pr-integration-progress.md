# Progression de l’intégration des PRs

Chaque ligne est enregistrée dans le commit de la tâche concernée.

| Lot | Tâche | Livraison | Vérification |
|---|---|---|---|
| preserve-contributor-attribution | 1.1 | docs: record reviewed PR authors and integration plan | Métadonnées des dix PRs relues via GitHub ; auteurs, SHA et états concordants |
| preserve-contributor-attribution | 1.2 | docs: fix installation and release repository links | Liens README vérifiés ; notice MIT et LICENSE conservés |
| preserve-contributor-attribution | 1.3 | docs: define adaptation provenance and attribution trailers | Registre par lot, SHA sources, modèle de description et règles auteur explicités |
| preserve-contributor-attribution | 2.1 | docs: verify contribution source and identity register | Liens locaux et dix SHA vérifiés ; métadonnées GitHub concordantes ; aucune adresse inventée |
| preserve-contributor-attribution | 2.2 | docs: prepare credited release description and notes | Notes de livraison distinguant réalisé et planifié ; aucun message externe publié |
| extend-schedule-editing | 1.1 | feat: target inactive schedules by name or ID | 49 tests services/ciblage réussis sur HA 2026.10 ; Ruff passe |
| extend-schedule-editing | 1.2 | feat: validate complete timetable and planning temperature payloads | 13 tests ciblés passent ; Ruff ; JSON et limites validés |
| extend-schedule-editing | 1.3 | feat: save complete schedules through confirmed shared mutations | 107 tests services/mutations passent ; erreurs et températures vérifiées ; Ruff |
| extend-schedule-editing | 2.1 | feat: refresh schedule labels while preserving registry identities | 16 tests ciblés réussis ; vrai registry, IDs et noms personnalisés préservés |
| extend-schedule-editing | 2.2 | feat: expose complete weekly planning data with room names | 17 tests ciblés passent ; summary réel, héritage dimanche/lundi et sept jours vérifiés |
| extend-schedule-editing | 3.1 | test: cover full schedule save concurrency and lifecycle | 111 tests planning/services passent sur les deux HA ; concurrence number/refresh/unload ; Ruff |
| extend-schedule-editing | 3.2 | docs: deliver credited extended planning services and validation | 357 tests réussis sur HA 2024.6.4 et 2026.10.4 ; Ruff passe |
| add-hourly-energy-statistics | 1.1 | feat: define stable external hourly statistics identities | Contrat IDs/source/métadonnées confronté aux APIs recorder et énergie des deux HA ; Ruff |
| add-hourly-energy-statistics | 1.2 | test: validate external hourly series on native HA recorders | 35 tests prototype/import/compilateur passent sur chaque HA ; schéma énergie et métadonnées natifs |
| add-hourly-energy-statistics | 2.1 | feat: collect and stage bounded hourly energy series | 31 tests HTTP/staging/API passent ; Ruff ; chunks et doublons vérifiés |
| add-hourly-energy-statistics | 2.2 | test: cover hourly staging edges and de-flake optimism expiry | 20 tests horaires sur les deux HA ; DST 23/25 h, délai 15 min, non-finis, réponses tardives ; 377 tests ; Ruff |
| add-hourly-energy-statistics | 3.1 | feat: replace external hourly series in acknowledged transactions | Vrai worker recorder des deux HA : création, idempotence, continuité, rollback sans métadonnée ; 387 tests ; import quotidien inchangé ; Ruff |
| add-hourly-energy-statistics | 3.2 | feat: add opt-in hourly updater, service granularity and home total | 17 tests import/updater/service/options ; total domicile refusé si pièce incomplète ; fenêtre 48 h/7 j lue du recorder ; 404 tests sur les deux HA ; Ruff |
| add-hourly-energy-statistics | 3.3 | test: cover hourly concurrency, cancellation, rename and resume | Manuel/updater et deux domiciles avec unload ; annulation fetch/INSERT/Store drainée sans écriture ; renommage et reprise depuis le recorder ; 410 tests sur les deux HA ; Ruff |
| add-hourly-energy-statistics | 4.1 | docs: document hourly statistics, recovery and the 1hour scale | 115 tests ciblés puis 410 tests sur HA 2024.6.4 et 2026.10.4 ; Ruff ; pip check (2024), 114 contraintes concordantes (2026, sans pip) ; liens vérifiés |
| add-hourly-energy-statistics | 4.2 | docs: deliver credited hourly energy statistics | Trailers TheFab21 #22/#24 sur les huit commits du lot ; CONTRIBUTORS, plan 21/36 et notes de livraison avec révisions sources ; hashes vérifiés |
| add-energy-cost-statistics | 1.1 | feat: define explicit energy price and cost conventions | 24 tests contrat (prix négatifs, unités, prix à l’heure, trous, tarif fixe, coûts non arrondis) ; 434 tests sur les deux HA ; Ruff |
