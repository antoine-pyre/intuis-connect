# Provenance des adaptations

Chaque livraison indique le lot, les fonctionnalités, les fichiers effectivement
adaptés, la PR et sa révision source, puis les commits d’implémentation locaux.
Le journal [pr-integration-progress.md](pr-integration-progress.md) suit les tâches ;
`git log --format=full` fournit les commits et leurs trailers.

| Lot | Auteur source | Révisions de référence |
|---|---|---|
| Planning étendu | TheFab21 | #22 `3174384d9222bdca5310721940ece95fe6d1fce6`, #24 `fb39b93c1eaf2a498c7274210b566864a2497669` |
| Énergie horaire | TheFab21 | #22 et #24 aux mêmes révisions |
| Coûts | TheFab21 | #22 et #24 aux mêmes révisions |
| Interface planning | TheFab21 | #17 `75ae980bd22c98b3fa42bb9f933c044d2c648c58`, #22 et #24 |

Les liens complets et les contributions antérieures figurent dans
[CONTRIBUTORS.md](../CONTRIBUTORS.md). Les lignes ci-dessus désignent des sources,
pas des fonctions livrées. Toute source additionnelle (notamment le fork
adrienvsj) doit être ajoutée avec sa révision avant adaptation.

Une adaptation conserve l’identité de son auteur d’implémentation. Trailers :

```text
Adapted-from: https://github.com/antoine-pyre/intuis-connect/pull/22
Original-author: @TheFab21
```

Conserver les notices des fichiers réutilisés et la licence MIT du projet.
Ne pas fabriquer de signature ou d’adresse pour Co-authored-by. Pour un commit
repris sans réécriture, conserver l’auteur Git original ; indiquer la source.
Une description de livraison contient : problème, comportement nouveau,
compatibilité, sources et adaptations, vérifications réelles et limites.
