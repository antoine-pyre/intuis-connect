# Tasks

Toutes les tâches d’implémentation restent ouvertes. Les documents présents ne constituent pas leur réalisation.

## 1. Contrat et prototype recorder

- [ ] 1.1 Définir identifiants externes, métadonnées, propriété des séries et comportement de sélection dans le tableau énergie, sans changer les capteurs journaliers.
- [ ] 1.2 Valider un prototype avec le vrai worker/compilateur HA sur les deux versions ; consigner la preuve du contrat et les limites avant le développement complet.

## 2. Collecte et staging

- [ ] 2.1 Ajouter le parseur horaire strict, les chunks bornés, les doublons identiques/contradictoires, les erreurs typées et les limites de débit.
- [ ] 2.2 Tester heures closes, délai de consolidation, fuseaux, DST 23/25 heures, zéro, trous, non-finis et réponses cloud tardives.

## 3. Import et updater

- [ ] 3.1 Étendre le chemin recorder externe avec transaction, sommes continues, acquittement et idempotence ; conserver intégralement l’import quotidien actuel.
- [ ] 3.2 Ajouter granularity et ses alias au service, options opt-in, intervalle, updater 48 heures/rattrapage 7 jours et isolation par entrée ; fournir un cumul horaire de domicile distinct avec contrôle des pièces incomplètes.
- [ ] 3.3 Tester import/updater concurrents, annulation fetch/INSERT/Store, renommage de capteur et reprise sans stockage auxiliaire.

## 4. Livraison

- [ ] 4.1 Exécuter les tests ciblés puis la matrice complète, Ruff et dépendances ; documenter choix de série, reprise, API et distinction avec scale 1hour.
- [ ] 4.2 Tracer précisément les adaptations de TheFab21 (#17/#22/#24) dans commits, crédits et notes de version avant livraison.
