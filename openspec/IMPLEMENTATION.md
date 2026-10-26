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

## Dérogations et état climate — 26 octobre 2026

- Agent : `heating_overrides`, changement `reconcile-heating-overrides`.
- Review : identité du dictionnaire vide, interface commune, sérialisation par pièce,
  intentions confirmées et persistance, optimisme 120 secondes, callbacks et retrait.
- Corrections demandées puis testées : réponse API tardive après retrait, snapshot
  de stockage, expiration observée lorsqu’elle est fournie, course prolongation/
  commande et protection contre la suppression d’une nouvelle intention.
- Validation indépendante : 257 tests réussis sur chacune des deux versions HA,
  Ruff et diff-check réussis ; 16 nouveaux tests emploient coordinateur/mapping/Store
  natifs avec transport de commande simulé.
- Format de stockage et identifiants préservés. Limite documentée : sans mode ni
  expiration permettant de le distinguer, un changement externe strictement
  identique à l’intention précédente ne peut pas être reconnu.

## Édition des plannings — 26 octobre 2026

- Agent : `schedule_mutations`, changement `correct-schedule-mutations`.
- Review : transformation cyclique semi-ouverte, suppression des transitions
  internes, restauration de la zone finale et préservation hors intervalle.
- Chemin partagé service/number : validation des demi-degrés, copie sous verrou,
  résolution du modèle courant et publication après succès cloud uniquement.
- Points demandés couverts : entrée non mutée, vérification minute par minute,
  dimanche/minuit, absence d’offset zéro, alias day, concurrence service/number
  avec remplacement du modèle pendant une requête.
- Validation indépendante : 299 tests réussis sur chacune des deux versions HA,
  Ruff et diff-check réussis ; 42 nouvelles régressions.
- La vérification HA récente initialement empêchée par une limite de la revue
  automatique a pu être relancée et a réussi après reprise de la conversation.
- Limite documentée : sérialisation locale ; l’API ne fournit pas de mécanisme
  de comparaison atomique avec les modifications provenant de l’application Intuis.

## Services multi-domicile — 26 octobre 2026

- Agent : `multi_home_services`, changement `fix-multi-home-service-contracts`.
- Review : cinq schémas home_id, descriptions statiques et traductions, résolution
  des données courantes, défauts sans cible et cycle de vie des inscriptions.
- Points demandés couverts : refus des cibles explicitement vides, validation des
  pièces avant lancement d’import, snapshots des entrées et gardes après réponse
  tardive, installation en lecture seule, ajout et retrait des entrées.
- Validation indépendante : 345 tests réussis sur chacune des deux versions HA,
  Ruff et diff-check réussis ; 46 nouvelles régressions par services enregistrés.
- Précision documentée : room_name sans home_id filtre les domiciles contenant
  cette pièce. Les services sans cette restriction conservent leurs défauts
  historiques ; les mutations de planning sans cible avertissent et choisissent
  la première entrée chargée.
