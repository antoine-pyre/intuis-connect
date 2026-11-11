# Intuis Connect 2.1.0 bêta

Cette préversion cumule les correctifs du client API préparés pour la 2.0.2 et
les corrections/diagnostics des issues #31 et #23 et le support fil pilote FP4
de #27. La stable reste la 2.0.1. Cette mise à jour regroupe le lot FP4
initialement préparé sur une branche 2.2.0 séparée.

## Planning et compatibilité Home Assistant — #31

- Une écriture en attente du verrou est refusée si son entrée a été rechargée
  ou déchargée ; un acquittement tardif ne modifie pas l'ancien modèle.
- Même protection pour les entités de température de zone retirées.
- Régressions couvrant un planning inactif avec espace final dans le nom,
  les ambiguïtés/incohérences nom-ID et les écritures concurrentes.
- L'appareil domicile est enregistré avant les plateformes, pour garantir le
  lien des températures de zone restaurées au démarrage.
- Utilisation de via_device_id et des propriétés climate natives lorsque le Core
  les propose, avec maintien de la compatibilité HA 2024.6.

## Historique énergétique et diagnostics — #23

- Rapport du dernier import quotidien par pièce : période demandée, échantillons
  reçus, jours mesurés/importés/manquants, statut et stade/type d'erreur.
- Diagnostics téléchargeables depuis Home Assistant, sans identifiants cloud,
  noms de pièces, compte, tokens ou messages d'exception.
- Validation des imports partiels : les pièces en erreur conservent leur
  historique, et un réimport ciblé ne modifie pas les autres pièces.
- Ce travail facilite le diagnostic du signalement #23 ; il ne prouve pas que
  les données historiques absentes sont disponibles sur le compte de l'auteur.

Le rapport détaillé concerne l'import quotidien et reste en mémoire jusqu'au
rechargement, ou jusqu'au prochain import quotidien.

## Support fil pilote — #27

- Détection des pièces de type FP sans température mesurée ni consigne, avec un
  ordre therm_setpoint_fp reconnu. Les FP avec températures gardent le thermostat.
- Presets Comfort, Eco et Hors-gel, sans cadran de température. Heat sélectionne
  Comfort manuel ; Auto reprend le planning ; Off conserve la commande existante.
- Commandes manual avec ordre comfort/away/frost_guard, échéance et aucune
  température numérique. Boost et consignes de température sont refusés pour
  les seules pièces fil pilote.
- Verrou partagé, affichage optimiste borné, acquittement vérifiant l'ordre et
  l'échéance, stockage/rechargement et réapplication des intentions fil pilote.
- Conservation des identifiants d'entités et des anciennes intentions thermiques.

## Robustesse des données partielles

Pièces sans définition ignorées sans crash, températures nulles conservées comme
inconnues, disponibilité climate liée à la présence de la pièce. Une réponse de
statut incomplète ne supprime pas les intentions des pièces encore définies.

## Correctifs client API hérités de la 2.0.2 bêta

- Les opérations de planning utilisent le serveur authentifié, y compris après
  bascule vers le serveur secondaire.
- Le renouvellement OAuth transmet aussi la version d'application.
- Les commandes de chauffage et de changement de planning remontent les refus
  applicatifs contenus dans une réponse HTTP 200.
- La réponse de commande de chauffage est lue et libérée après réception.

## Validation et crédits

570 tests réussis sur HA 2024.6.4 / Python 3.12 et HA 2026.10.4 / Python 3.14,
14 tests JavaScript, Ruff et cohérence des dépendances. Les régressions utilisent
les vrais services, registries, Store et recorder SQLite, avec transport cloud
simulé. Les hooks de conversion climate récents sont aussi exercés avec une base
simulée ; la validation sur un Core exposant réellement la nouvelle API reste à
faire. Aucun compte cloud ni radiateur réel n'a été sollicité. Docker n'était pas
disponible ; une configuration isolée est fournie pour une validation ultérieure.

Les diagnostics et la création anticipée de l'appareil parent adaptent les apports
de **adrienvsj**, avec sources dans CONTRIBUTORS.md et docs/14-diagnostics.md.
Les limites de contrat API sont détaillées dans docs/13-apk-api-audit.md.

Le FP4 adapte la proposition **apeyrat #27** et les corrections de détection et
de données partielles d’**adrienvsj**. La détection reste une heuristique au
démarrage ; l’acceptation des ordres FP4 sur matériel réel reste à confirmer.
Les détails et sources sont dans docs/15-pilot-wire.md et CONTRIBUTORS.md.

Si une copie précédente de cette même 2.1.0 bêta est déjà installée,
retélécharger la version puis redémarrer Home Assistant pour obtenir le lot FP4.
