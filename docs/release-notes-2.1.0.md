# Intuis Connect 2.1.0 — intégration dépréciée / deprecated

## Statut du projet

Cette version publie en stable le contenu de la bêta 2.1.0. L'intégration cloud
est désormais **dépréciée** : le mainteneur a migré vers Zigbee2MQTT et ne dispose
plus d'installation Intuis cloud compatible pour valider les évolutions.
La maintenance future et la compatibilité avec les évolutions de Home Assistant
ou de l'API cloud ne sont pas garanties. Les contributions testées sur du matériel
compatible restent les bienvenues.

Les installations existantes peuvent continuer à fonctionner tant que l'API
cloud reste compatible ; aucune date d'arrêt n'est fixée. Pour les appareils
compatibles, suivre le [guide de migration Zigbee](https://github.com/antoine-pyre/intuis-connect/blob/v2.1.0/docs/16-zigbee-migration.md).
**Exporter tous les plannings avant de déconnecter le premier radiateur.**
La compatibilité Zigbee n'est pas établie pour tous les anciens modules et
systèmes fil pilote.

**English:** the cloud integration is now deprecated. The maintainer has migrated
to local Zigbee control and has no compatible cloud installation for testing.
Future maintenance and compatibility are not guaranteed; tested contributions
remain welcome. Existing installations may continue to work while the cloud API
remains compatible. Export all schedules before migrating compatible devices.

## Changements depuis la stable 2.0.2

- Support fil pilote FP4, détection distinguant les pièces sans températures,
  presets et libellés/icônes ; validation réelle partielle rapportée dans #27.
- Protections de ciblage et de concurrence des plannings lors des rechargements,
  et adaptation aux dépréciations Home Assistant (#31).
- Diagnostics et export de tous les plannings chargés pour préparer la migration.
  Le fichier exporté contient les noms et les habitudes de chauffe : le relire
  avant tout partage public.
- Réponse getconfig sans modules : conservation de la dernière configuration
  valide avec fraîcheur explicite, sans interrompre les données des pièces (#38).
- Pièces sans dispositif de mesure : exclusion des imports et des totaux horaires
  mesurables, sans consommation nulle inventée (#36). Agrégat quotidien inchangé.
- Guide Zigbee enrichi par #39 : appairage Intuis 3.0, firmware adapté au matériel
  (dont le cas 2.0.5), reporting et lecteur de sauvegarde Android durci.
- Le correctif du timer des statistiques horaires (#35/#37), déjà livré en
  stable 2.0.2, est conservé.

## Limites et crédits

#31 reste en attente de confirmation terrain du ciblage sur une copie de planning.
Le convertisseur vers les helpers HA de #33 n'est pas inclus. Les tests automatisés
ne remplacent pas une validation cloud/matérielle ; le lecteur Android est testé
sur des archives synthétiques, sans téléphone réel.

Merci à apeyrat, adrienvsj et jneuveglise pour les contributions et validations.
Les commits originaux et les adaptations sont référencés dans CONTRIBUTORS.md.

## Validation de la publication stable

603 tests Python réussis sur chacune des matrices HA 2024.6.4 / Python 3.12.15
et HA 2026.10.4 / Python 3.14.4, 14 tests JavaScript et Ruff réussis.
La fusion avec la stable 2.0.2 conserve le correctif du timer et les contributions
de la bêta ; le seul conflit concernait le numéro de version, résolu en 2.1.0.
