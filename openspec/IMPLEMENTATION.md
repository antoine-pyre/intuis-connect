# Journal d’implémentation et de review

Branche : `codex/reliability-fixes`. Les développements sont confiés à des agents
dédiés séquentiellement ; chaque livraison est relue avant commit par l’agent principal.
Aucun push, déploiement ni appel vers un compte Intuis réel n’est effectué.

## Socle de validation — 26 octobre 2026

- Agent : `quality_foundation`, groupe 1 de `strengthen-quality-workflow`.
- Review : fixtures natives HA, contraintes et CI, fallback recorder historique,
  nettoyage des imports et absence de changement métier hors compatibilité.
- Corrections demandées en review : isoler la génération de services.yaml dans les
  tests ; retirer les pins contradictoires ; vérifier une installation historique vierge.
- Validation indépendante : 197 tests réussis sur HA 2024.6.4/Python 3.12.14 et
  HA 2026.10.4/Python 3.14.4 ; Ruff et diff-check réussis.
- Le smoke SQLite couvre une transaction, pas encore la queue du worker recorder.
  Le lot import doit vérifier le traitement réellement exécuté par ce worker.
- CI distante non exécutée à ce stade ; les commandes de la matrice ont été exécutées localement.

## API et cache énergétique — 26 octobre 2026

- Agent : `api_energy`, changement `harden-api-and-energy-cache`.
- Review : conservation des paramètres du retry 401, libération des réponses,
  parsing strict, erreurs vs zéro, cache par pièce, disponibilité et agrégats.
- Points demandés en review couverts : échec global du coordinateur, reprise des
  seules pièces échouées, journée du domicile, max journalier après valeur ancienne,
  agrégat incomplet et absence initiale de mesure.
- Validation indépendante : 225 tests réussis sur chacune des deux versions HA,
  Ruff et diff-check réussis. Les nouveaux tests emploient de vrais ClientResponse
  via le transport simulé, sans appels vers Intuis.
- L’import reçoit désormais des erreurs typées ; son remplacement transactionnel
  reste à réaliser dans le changement suivant.

## Import historique sécurisé — 26 octobre 2026

- Agent : `history_import`, changement `secure-energy-history-import`.
- Review : transaction recorder atomique, confirmation après commit/rollback,
  couverture des jours locaux clos, baselines et continuité des sommes, concurrence
  des services et arrêt des tâches lors du déchargement.
- Corrections demandées puis testées : validation défensive du staging, libération
  de l’ownership en appel direct, annulation avant démarrage et pendant INSERT,
  refus d’un worker arrêté, drain des sauvegardes Store et création unique du manager.
- Validation indépendante : 242 tests réussis sur chacune des deux versions HA,
  Ruff et diff-check réussis ; 34 tests import font appel au véritable worker
  recorder, SQLite et au compilateur de statistiques sensor.
- Limite assumée : refus sans baseline short-term live valide après la période,
  sans couverture exacte des jours locaux ou pour des bornes non horaires.
  Le premier import automatique peut nécessiter une reprise manuelle après les
  premières statistiques live. Voir docs/08-safe-energy-history-import.md.
