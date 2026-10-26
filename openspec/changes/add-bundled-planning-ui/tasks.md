# Tasks

Toutes les tâches d’implémentation restent ouvertes. Les documents présents ne constituent pas leur réalisation.

## 1. Adaptation du frontend

- [ ] 1.1 Inventorier les comportements HTML #22/#24 et adapter la grille/horaires/zones aux summaries et services étendus.
- [ ] 1.2 Ajouter sélection du domicile, mode intégré/autonome, état dirty, sauvegardes confirmées/partielles et rafraîchissement/reconnexion.
- [ ] 1.3 Corriger les insertions HTML de données cloud ; implémenter la gestion explicite des tokens et la déconnexion.

## 2. Distribution

- [ ] 2.1 Ajouter la vue HTTP, dépendance http si requise, assets embarqués et ETag/304 sans lecture bloquante.
- [ ] 2.2 Tester multi-entrée, reload, dernier unload, fichiers absents et nouvelle version sans données secrètes dans la coque.

## 3. Validation et livraison

- [ ] 3.1 Tester la logique JavaScript et les parcours HTTP, puis iframe et autonome sous Firefox/Chromium : minuit/semaine, erreurs, token, sauvegarde, cache et retour après redémarrage.
- [ ] 3.2 Exécuter la matrice backend, Ruff et les contrôles frontend ; documenter dashboards et migration facultative des anciennes copies HTML.
- [ ] 3.3 Conserver le crédit TheFab21 dans l’interface, les sources et les notes de version ; relier chaque adaptation à ses PRs/révisions avant livraison.
