# Revue du fork et des issues restantes — 11 novembre 2026

Revue en lecture seule du code produit : aucune fonctionnalité intégrée et aucun
message GitHub publié. Référence stable : v2.0.1 (4e84d62). Branche locale :
fix/api-client, 02795b7 (v2.0.2-beta). Fork examiné :
adrienvsj/intuis-connect, main à 0793654090. Les quatre issues ouvertes sont
#23, #27, #28 et #31.

## Ce que l'on peut avancer sans retour utilisateur

| Issue | Travail réalisable | Ce qui demande encore une validation externe |
|---|---|---|
| [#31](https://github.com/antoine-pyre/intuis-connect/issues/31) | Tester deux plannings dont un inactif avec espace final, ID/nom incohérents, noms identiques, appels concurrents et rechargement pendant une écriture. Auditer la source du modèle avant envoi. Migrer les dépréciations HA avec compatibilité 2024.6. | Vérifier le scénario original sur l'installation et le contrat serveur de synchronisation. |
| [#27](https://github.com/antoine-pyre/intuis-connect/issues/27) | Adapter le support fil pilote d'apeyrat et sa correction de détection par adrienvsj : parsing des ordres, presets, payload sans température, dérogations persistantes et tests. | Vérifier les commandes sur du matériel FP4 réel et les variantes FP non testées. |
| [#23](https://github.com/antoine-pyre/intuis-connect/issues/23) | Ajouter des diagnostics d'import par pièce : dates demandées/reçues, données manquantes, capteur enregistré, erreurs API/recorder. Vérifier par tests que deux pièces réussissent et quatre échouent sans perte ni succès global trompeur. | Connaître la cause du manque d'historique de cet utilisateur : données cloud, transport, éligibilité des pièces ou recorder. |
| [#28](https://github.com/antoine-pyre/intuis-connect/issues/28) | Recenser les apports du fork absents du dépôt, adapter diagnostics et robustesse utiles, conserver les auteurs et les sources. | Discussion de maintenance, intentions du mainteneur du fork et tests matériels éventuels. |

## Apports du fork vérifiés

- [`6eb642b735`](https://github.com/adrienvsj/intuis-connect/commit/6eb642b73539cee2c642b80e7bbb2dbbcd35695d) — climate: support pilot-wire (FP4) radiators with order presets
- [`04b79ef755`](https://github.com/adrienvsj/intuis-connect/commit/04b79ef755ae794240c6fa1507a1a5fce1e5b139) — Only treat rooms without temperatures as pilot-wire (2.1.1)
- [`598e635929`](https://github.com/adrienvsj/intuis-connect/commit/598e6359298493a9dd0c1da03dfb14619603d748) — Harden the coordinator and climate entities against partial data
- [`c58382bd54`](https://github.com/adrienvsj/intuis-connect/commit/c58382bd54b1c2fdf3c3e3a6026547cdeb9844fd) — Fix history import side effects and daily energy fallbacks
- [`acc734719c`](https://github.com/adrienvsj/intuis-connect/commit/acc734719c7e0484c949f89fc6d9a1a910c67252) — Add diagnostics and remove dead code
- [`d5dc5b5a90`](https://github.com/adrienvsj/intuis-connect/commit/d5dc5b5a90e80d4b0dfa24e3d799c60a1fb2ffde) — Use OptionsFlowWithReload and the reauth helper

### FP4 : apport fonctionnel réel

La classe IntuisPilotWireClimate expose des ordres au lieu d'une consigne ;
le client accepte therm_setpoint_fp pour une commande manual sans température.
Les dérogations enregistrent et réappliquent l'ordre. Des tests climate/API
accompagnent le changement.

La correction 04b79ef755 exige un type FP et l'absence des deux températures.
Elle évite de supprimer le thermostat des appareils FP qui fournissent des
températures. Ce critère reste une heuristique : une réponse cloud temporairement
incomplète doit être testée pour éviter une mauvaise classification au démarrage.

Notre moteur de dérogations/réconciliation a été réécrit : adapter le contrat
d'ordre dans overrides.py et les états climate actuels, sans remplacer ces
mécanismes par ceux de l'ancien socle du fork.

### Robustesse : trous encore visibles localement

598e635929 protège le mapper contre une pièce sans définition et conserve les
températures absentes/null à None. Localement, le mapper appelle encore
IntuisRoom.from_dict avec une définition potentiellement absente ; la méthode
accède directement à definition.module_ids. Les températures utilisent encore
des défauts 0.0 et les comparaisons ne protègent pas les valeurs null explicites.
Ces protections sont utiles indépendamment des retours sur #27/#23.

Adapter aussi les consommateurs (climate, capteurs, estimation de chauffage),
et tester la disparition temporaire des pièces. Le set global de warnings du
fork ne doit pas être repris sans examen de son cycle de vie.

### Diagnostics : apport utile à #23 et #31

acc734719c ajoute le téléchargement de diagnostics HA avec masquage du compte,
du token et de la localisation, un résumé du domicile et l'état des pièces.
Cette plateforme est absente localement. Elle fournit une base, mais son accès
aux ancres horaires privées n'est pas compatible avec notre implémentation ;
il faut exposer nos propres états d'import et pseudonymiser les identifiants
et libellés sensibles dans la version adaptée.

### Énergie : plusieurs doublons

Les besoins traités par c58382bd54 (erreurs non converties en zéro, import
interrompu sans trous silencieux, nettoyage des indicateurs, frontières de
requêtes) recoupent nos imports transactionnels, la validation et la disponibilité
par pièce. Ne pas reprendre globalement history_import.py ni l'ancien mécanisme
de cumul. Vérifier les scénarios manquants avant toute adaptation.

L'import actuel possède déjà erreurs, rooms_imported, days_without_data et les
statuts partial/failed ; l'enjeu proposé est de rendre le diagnostic plus fin
et facilement récupérable, pas d'annoncer que ces informations n'existent pas.

### Compatibilité et dépréciations

Le fork cible HA 2026.10 alors que notre minimum reste 2024.6.
Son changement OptionsFlowWithReload/reauth est une piste à évaluer avec une
couche de compatibilité et la matrice existante ; pas un remplacement direct.
Il ne constitue pas une solution vérifiée aux deux dépréciations de #31 :
le code du fork examiné utilise encore d'anciennes propriétés climate.

## Ordre proposé des lots

1. #31 : régressions de ciblage/rechargement, puis corrections nécessaires ;
   migration HA dans un changement distinct.
2. Robustesse des données partielles puis #27 : modèle/API, dérogations, entité
   fil pilote, tests et documentation.
3. #23 : diagnostics anonymisés et couverture des imports partiels.
4. #28 : bilan des adaptations, attribution apeyrat/adrienvsj, puis réponse
   de collaboration à relire avant publication.

Chaque lot doit garder les identités d'entités et les statistiques existantes,
enregistrer les révisions sources effectivement adaptées et passer les tests
pertinents sur les versions HA supportées. La réussite des tests hors ligne
ne vaut pas confirmation sur le matériel ou le compte cloud des auteurs.

