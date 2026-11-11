# Validation 2.1.0 bêta — 11 novembre 2026

Branche : codex/2.1.0-beta, construite sur fix/api-client à 02795b7.
La première publication isolait les correctifs client 2.0.2 et les issues #31
et #23 (546 tests par Core). À la demande du mainteneur, la mise à jour de cette
même bêta fusionne aussi le lot FP4/#27 de codex/2.2.0-beta (570 tests par Core).
Aucune release 2.2.0 séparée n’est créée.

## Revue et couverture

Deux sous-agents ont revu indépendamment le lot planning et le lot diagnostics.
Aucun problème actionnable restant n'a été identifié. Le FP4, initialement
séparé, a aussi fait l'objet d'une revue croisée et est maintenant inclus.
La revue croisée initiale avait trouvé une course dans l'enregistrement du parent
avant les plateformes : son correctif et son test sont inclus ici.

- #31 : services et numbers refusent les écritures restées en attente après
  remplacement de l'entrée ; les acquittements tardifs ne modifient pas l'ancien
  modèle. Ciblage inactif/espace final, noms-ID incohérents, concurrence et lien
  au parent d'un number déjà activé sont testés.
- #31 : API via_device_id et climate native_* utilisées lorsqu'elles existent,
  avec fallback minimum. Deux régressions isolent l'API héritée et une base
  simulant la conversion des températures ; Heat envoie les degrés natifs,
  jamais les valeurs converties pour affichage.
- #23 : diagnostics anonymisés et rapport par pièce du dernier import quotidien.
  Deux succès/quatre erreurs préservent les statistiques des pièces en échec ;
  le réimport ciblé n'altère que la pièce choisie.

## Résultats de la branche regroupée

| Validation | Résultat |
|---|---|
| HA 2024.6.4 / Python 3.12.15 | 570 tests pytest réussis, aucun ignoré |
| HA 2026.10.4 / Python 3.14.4 | 570 tests pytest réussis, aucun ignoré |
| Logique JavaScript Node 24.22.1, passe commune précédente | 14 tests réussis |
| Ruff et cohérence des dépendances | Réussis sur les deux environnements |
| git diff --check | Réussi |

Les services, registries, Store et recorder SQLite sont réels ; le transport
cloud est simulé. Les sockets externes restent interdits par pytest-socket.
Le démarrage des workers HA nécessite ici une exécution hors sandbox.
L'environnement minimum est reconstitué hors ligne depuis le cache et les
contraintes du dépôt, avec pip check réussi.

La passe commune précédente (avant séparation FP4) comptait 568 tests réussis
sur chaque version et 54/54 vérifications dans chacun de Chromium et Firefox,
en autonome et iframe. Le harness utilise les vrais services/vue, mais simule
le cloud et le cadre du dashboard. L'attente longue de 45 secondes n'a pas été
rejouée. La fermeture Firefox passe désormais par BiDi pour éviter l'erreur
SIGTERM du lanceur snap.

Le lot #27 vérifie la sélection FP4 sans supprimer le thermostat des FP avec
températures, les ordres sans température, leurs refus/acquittements, la
persistance et la réapplication, ainsi que la récupération après statut partiel.

## Limites

- L’acceptation des ordres FP4 sur matériel réel reste à confirmer.
- Le scénario cloud exact de #31 et la disponibilité de l'historique du compte
  de #23 nécessitent encore un retour utilisateur.
- Les deux cores installés utilisent l'API climate héritée. La régression sur
  une base native simulée ne remplace pas une exécution sur un Core plus récent.
- Les rapports détaillés concernent le dernier import quotidien, restent en
  mémoire jusqu'au reload et sont remplacés au prochain import quotidien.
- Docker est absent du poste, confirmé par l'utilisateur. Les YAML Docker ont
  été parsés et relus ; builds, démarrage et healthcheck ne sont pas exécutés.
  Les runners ne pilotent pas l'instance HTTP vierge du compose.

Voir [diagnostics](14-diagnostics.md), [développement](development.md),
[revue du fork](fork-review-2026-11-11.md) et [CONTRIBUTORS](../CONTRIBUTORS.md).
