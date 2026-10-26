# Tasks

Priorité : **P1/P2** — Review : **R4, R8**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../README.md) avant implémentation. Toutes les tâches restent à faire.

## 1. Régressions HTTP et énergie

- [ ] 1.1 Créer des tests du vrai client avec transport simulé : serveur énergie avec query, JSON/formulaire, en-têtes, timeout et token remplacé après 401.
- [ ] 1.2 Couvrir 401 répété, échec de renouvellement, 429, 5xx et timeouts sans dépendre d’un compte réel.
- [ ] 1.3 Tester une panne par pièce puis une reprise au cycle suivant, une réponse partielle et une mesure valide de zéro.

## 2. Contrats et implémentation

- [ ] 2.1 Corriger le retry 401 pour préserver tous les paramètres de requête et limiter le renouvellement à une tentative.
- [ ] 2.2 Inventorier puis migrer les appelants du client énergétique vers un résultat distinguant succès, zéro et indisponibilité.
- [ ] 2.3 Supprimer les fallbacks 0.0 sur erreurs de transport/parsing et maintenir une gestion explicite des erreurs par pièce.
- [ ] 2.4 Passer le cache journalier à un suivi de succès par pièce et conserver la dernière mesure valide sans cacher un échec jusqu’au lendemain.
- [ ] 2.5 Adapter les capteurs à l’absence initiale de valeur et à la fraîcheur des dernières mesures valides.

## 3. Validation

- [ ] 3.1 Exécuter les tests API/cache/capteurs et ceux de l’import historique, puis la suite complète.
- [ ] 3.2 Documenter les règles de cache, de reprise et de mesure indisponible.
