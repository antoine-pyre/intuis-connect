# Intuis Connect 2.0.2

Correctif ciblé des statistiques horaires automatiques (#35, PR #37).
Le listener du timer HA est maintenant un callback exécuté dans la boucle
asyncio : la tâche de mise à jour peut démarrer, sans erreur de thread.
Les imports manuels conservent leur comportement.

Le correctif et son test passant par un vrai timer proviennent d'adrienvsj
(PR #37, commit af3ef5f129d7f329634c0ba9646d87acc3bc436e), dont l'auteur
est conservé dans l'historique. Aucun autre changement fonctionnel de la bêta
2.1.0 n'est inclus dans cette version stable.

Après mise à jour et redémarrage de Home Assistant, les utilisateurs ayant
activé les statistiques horaires peuvent vérifier leur prochain cycle.
Les tests automatisés utilisent un cloud simulé ; la confirmation terrain reste
attendue dans #35/#37.

Validation : 520 tests réussis sur HA 2024.6.4 / Python 3.12.15 et
HA 2026.10.4 / Python 3.14.4, avec Node 22.14.0 disponible pour la parité
JavaScript. Ruff et la suite JavaScript passent également.
