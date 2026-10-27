# Tasks

Priorité : **P1/P2** — Review : **R4, R8**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../../README.md) avant implémentation. Les tâches ci-dessous ont été implémentées et validées localement.

## 1. Régressions HTTP et énergie

- [x] 1.1 Créer des tests du vrai client avec transport simulé : serveur énergie avec query, JSON/formulaire, en-têtes, timeout et token remplacé après 401.
- [x] 1.2 Couvrir 401 répété, échec de renouvellement, 429, 5xx et timeouts sans dépendre d’un compte réel.
- [x] 1.3 Tester une panne par pièce puis une reprise au cycle suivant, une réponse partielle et une mesure valide de zéro.

## 2. Contrats et implémentation

- [x] 2.1 Corriger le retry 401 pour préserver tous les paramètres de requête et limiter le renouvellement à une tentative.
- [x] 2.2 Inventorier puis migrer les appelants du client énergétique vers un résultat distinguant succès, zéro et indisponibilité.
- [x] 2.3 Supprimer les fallbacks 0.0 sur erreurs de transport/parsing et maintenir une gestion explicite des erreurs par pièce.
- [x] 2.4 Passer le cache journalier à un suivi de succès par pièce et conserver la dernière mesure valide sans cacher un échec jusqu’au lendemain.
- [x] 2.5 Adapter les capteurs à l’absence initiale de valeur et à la fraîcheur des dernières mesures valides.

## 3. Validation

- [x] 3.1 Exécuter les tests API/cache/capteurs et ceux de l’import historique, puis la suite complète.
- [x] 3.2 Documenter les règles de cache, de reprise et de mesure indisponible.

## Validation — 26 octobre 2026

- `python -m pytest` : **225 tests réussis** sur HA 2024.6.4/Python 3.12.14 et
  HA 2026.10.4/Python 3.14.4, dont 28 nouvelles régressions API/cache/capteurs.
- Les 17 tests existants de l’import historique restent inclus et réussis.
- `python -m ruff check .` et `git diff --check` : réussis.
- Les scénarios transport passent par `cloud_responses` avec de véritables
  ClientResponse ; sockets externes bloquées par pytest-socket.
- Couverture ciblée : retry 401 fidèle/limité, refus et timeout du refresh,
  429/500/timeouts, zéro valide, données vides/nulles/malformées, résultats
  partiels, récupération au cycle suivant, fraîcheur, fuseau/reset journalier,
  disponibilité globale du coordinateur et total domicile incomplet.
- L’import historique reçoit déjà ces erreurs via son handler `APIError`.
  Sa sécurité transactionnelle est traitée dans le changement suivant.
