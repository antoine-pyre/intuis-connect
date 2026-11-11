# Intuis Connect 2.0.2 bêta

Cette préversion porte les correctifs issus de la comparaison du client API
avec l’application officielle Intuis 2.8.0. La version stable reste la 2.0.1.

## Correctifs

- Les opérations de planning utilisent le serveur sur lequel la connexion a
  réussi, y compris après bascule vers le serveur secondaire.
- Le renouvellement OAuth transmet aussi la version d’application.
- Les commandes de chauffage et de changement de planning remontent les erreurs
  applicatives présentes dans une réponse HTTP 200.
- La réponse de commande de chauffage est lue et libérée après réception.

## Validation et limites

Treize nouveaux tests de transport couvrent ces correctifs. La validation ciblée
initiale compte 198 tests réussis sur Home Assistant 2026.10.4 ; les contrôles
de publication vérifient aussi la matrice HA 2024.6.4 / 2026.10.4 dans GitHub Actions.
La suite locale complète passe également : 530 tests réussis, deux tests ignorés
car Node.js n’est pas installé sur cette machine. Les tests JavaScript sont
exécutés en CI.

Aucun test sur le compte cloud ou les radiateurs réels n’a été effectué pour cet
audit. Des différences restent à vérifier concernant l’identité OAuth, la route
de récupération de l’énergie, le format des plannings et la portée des presets.
Les identifiants OAuth et les formats de données existants sont conservés.

Voir le [rapport et les preuves de l’audit](https://github.com/antoine-pyre/intuis-connect/blob/v2.0.2-beta/docs/13-apk-api-audit.md).
