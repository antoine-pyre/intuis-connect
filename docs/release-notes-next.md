# Notes de livraison en préparation

État : travail local, non publié. Ne pas présenter les éléments planifiés comme
livrés. Les tâches réalisées et leurs preuves sont suivies dans
[le journal](pr-integration-progress.md).

## Attribution et documentation réalisées

Les auteurs des dix PRs sont recensés avec leurs révisions dans
[CONTRIBUTORS.md](../CONTRIBUTORS.md). Les liens du dépôt pour HACS et les releases
sont harmonisés. Le crédit de création revient à Antoine Pyré ; les contributions
de tranb3r, halfred, chrislek, sremy91 et TheFab21 restent explicitement distinguées.
La licence MIT et ses notices sont conservées.

## Sources des prochains lots

Les services étendus, l’énergie horaire, les coûts et le planning HTML seront
adaptés des propositions de **TheFab21**, notamment
[#22](https://github.com/antoine-pyre/intuis-connect/pull/22) et
[#24](https://github.com/antoine-pyre/intuis-connect/pull/24), issues de
[#17](https://github.com/antoine-pyre/intuis-connect/pull/17).
Chaque livraison devra préciser ses adaptations et validations réelles, sans
annoncer une fusion des anciennes branches.

## Description de livraison — attribution et liens

Problème : les contributions proposées et intégrées n’étaient pas recensées et
plusieurs liens README visaient l’ancien nom du dépôt.

Résultat : registre de sources et règles d’attribution disponibles, liens
harmonisés, aucune modification de comportement ou d’identité d’entité.

Validation : métadonnées des dix PRs consultées, SHA/auteurs/statuts concordants,
liens locaux contrôlés et notices préservées. Aucun message externe publié.

## Planning étendu — réalisé localement

Adaptation des propositions de **TheFab21 #22/#24** : ciblage d’un planning
inactif par nom/ID, sauvegarde complète par `sync_schedule`, températures away/hg,
noms actualisés et summaries à sept jours avec noms de pièces. Les anciens
appels continuent de viser le planning actif. Les IDs et noms personnalisés
restent conservés. Les mutations partagent le verrou services/number existant.
La validation couvre schémas, erreurs, concurrence, refresh et retrait d’entrée.

## Énergie horaire — réalisé localement

Adaptation des propositions de **TheFab21**
([#22](https://github.com/antoine-pyre/intuis-connect/pull/22) à
`3174384d9222bdca5310721940ece95fe6d1fce6`,
[#24](https://github.com/antoine-pyre/intuis-connect/pull/24) à
`fb39b93c1eaf2a498c7274210b566864a2497669`, issues de
[#17](https://github.com/antoine-pyre/intuis-connect/pull/17)).

Problème : le scale `1hour` rafraîchit seulement les capteurs journaliers ; aucune
statistique horaire exacte ni import historique horaire n’existait.

Comportement nouveau : statistiques externes horaires par pièce et pour le
domicile, mise à jour facultative (désactivée par défaut, 120 min), relecture des
48 dernières heures closes et rattrapage jusqu’à 7 jours depuis le recorder, et
`granularity: daily|hourly` (alias `1day|1hour`) pour `import_energy_history`.

Compatibilité : capteurs journaliers, IDs, statistiques existantes, défaut
quotidien du service et import journalier inchangés. Désactiver l’option ne
supprime aucune statistique.

Sources et adaptations : reprises de TheFab21 — méthode API horaire découpée,
statistiques horaires périodiques avec intervalle, historique jusqu’à 730 jours
avec granularité et alias, total cumulé du domicile. Réécrits ici : identités
externes stables, validation stricte (heures closes, DST, doublons, trous),
remplacement transactionnel acquitté, reprise sans stockage auxiliaire et total
domicile refusé tant qu’une pièce manque. Commits d’implémentation : `0efa760`,
`d02eab9`, `4e4c49d`, `5ab1822`, `e570d36`, `b232d8c`, `c046590`, `6d26ad6`,
avec trailers `Adapted-from`/`Original-author`.

Vérifications : 410 tests sur HA 2024.6.4 et 2026.10.4, dont le vrai worker
recorder (rollback, annulation, concurrence, deux domiciles), Ruff et contraintes.

Limites : comportement réel du cloud et du matériel non éprouvé hors ligne ;
le libellé d’une série reste celui de sa création après renommage d’une pièce ;
la sélection dans le tableau énergie est validée côté schéma, pas dans le
navigateur.

## Coûts énergétiques — réalisé localement

Adaptation des propositions de **TheFab21**
([#22](https://github.com/antoine-pyre/intuis-connect/pull/22) à
`3174384d9222bdca5310721940ece95fe6d1fce6`,
[#24](https://github.com/antoine-pyre/intuis-connect/pull/24) à
`fb39b93c1eaf2a498c7274210b566864a2497669`, code coût identique entre les deux).

Problème : aucun coût, prix historique ni recalcul n’existait. Le code de #22
avait des sélecteurs rejetés par HA, une migration pouvant supprimer une entité
étrangère, un repli silencieux sur le prix courant et un service de recalcul
appelant une méthode absente.

Comportement nouveau : statistiques horaires de coût par pièce et pour le
domicile, depuis l’énergie horaire confirmée et un prix fixe ou un capteur
`<devise>/kWh` lu à chaque début d’heure ; capteurs d’affichage sans
`state_class` ; service `recalculate_cost_history` avec réponse.

Compatibilité : désactivé par défaut et dépendant des statistiques horaires ;
kWh, capteurs et identifiants existants inchangés. Les options, entités,
statistiques et fichiers créés par #22/#24 sont inventoriés et laissés intacts ;
aucune migration ne s’exécute.

Sources et adaptations : reprises de TheFab21 — prix fixe ou entité, historique
de prix via le recorder, capteur et statistiques de coût, recalcul de
l’historique. Réécrits ici : clés d’options distinctes, sélecteurs valides,
trou de prix refusé au lieu d’un repli, coûts dérivés des kWh confirmés, séries
externes en transaction acquittée, devise unique par série, réservation commune
avec les imports, publication publique après acquittement. Commits : `8e716b1`,
`a9d7d74`, `c3944a8`, `790f27b`, `b2ca359`, `1dcd500` et le commit de livraison,
avec trailers `Adapted-from`/`Original-author`.

Vérifications : 472 tests sur HA 2024.6.4 et 2026.10.4, dont le vrai worker
recorder (prix enregistrés, échec, annulation, devise, réimport), la réponse du
service réel et le schéma énergie ; Ruff et contraintes.

Limites : prix au début de l’heure (approximation intra-horaire documentée) ;
historique de prix limité à la rétention du recorder ; pas de coût par appareil
dans le tableau énergie de HA ; comportement réel non éprouvé hors ligne.

## Éditeur de planning embarqué — réalisé localement

Adaptation de l’éditeur HTML de **TheFab21**
([#17](https://github.com/antoine-pyre/intuis-connect/pull/17) à
`75ae980bd22c98b3fa42bb9f933c044d2c648c58`,
[#22](https://github.com/antoine-pyre/intuis-connect/pull/22) à
`3174384d9222bdca5310721940ece95fe6d1fce6`,
[#24](https://github.com/antoine-pyre/intuis-connect/pull/24) à
`fb39b93c1eaf2a498c7274210b566864a2497669`, fichier
`custom_components/intuis_connect/resources/intuis_planning.html` de #24).

Problème : l’éditeur visuel et sa distribution automatique étaient absents ; la
version source s’appuyait sur une route servant le fichier sans contrôle de
cycle de vie, sur des insertions HTML de noms cloud et sur un ETag lié à la seule
version du manifest.

Comportement nouveau : éditeur servi à `/api/intuis_connect/planning`, intégré
dans un dashboard (session HA) ou dans un onglet autonome (adresse et token
explicites) ; grille sept jours avec transitions de minuit et de fin de semaine,
domicile et planning sélectionnables, absence/hors-gel, températures par pièce,
modifications non enregistrées signalées, résultats de sauvegarde par étape,
rafraîchissement, thème clair/sombre et reconnexion bornée à 45 secondes.

Compatibilité : services, entités, identifiants et automatisations inchangés ;
attribut `home_name` ajouté au capteur de résumé ; dépendance `http` déclarée.
Les anciennes copies manuelles restent utilisables et peuvent être supprimées.

Sources et adaptations : reprises de TheFab21 — grille hebdomadaire, dialogue
de créneau, cartes de zones, absence/hors-gel, sélection du planning, détection
des modifications, modes iframe/autonome, option *Remember*, attente de 45 s et
distribution par route avec ETag. Réécrits ici : logique séparée et alignée sur
`timetable.py`, rendu exclusivement textuel, sauvegarde par étapes confirmées
avec succès partiel affiché, réconciliation des mises à jour distantes, domicile
sélectionnable, températures ciblées par identifiants (noms en double modifiables), token jamais dans l’URL et déconnexion,
route enregistrée une fois, servie seulement avec un domicile chargé, lectures
hors boucle, ETag de contenu et CSP. Logs de debug et code mort non repris.
Commits : `fe812f6`, `6ef6c45`, `f69a83e`, `f5c28d0` et `4670e9c`,
avec trailers `Adapted-from`/`Original-author`.

Vérifications : 491 tests sur HA 2024.6.4 et 2026.10.4 (vue HTTP réelle, cycle
de vie, parité JS/Python, contrat avec le capteur réel), 14 tests Node, Ruff ;
parcours autonome et iframe dans Chromium 156 et Firefox 158 sur les vrais
services HA (55/55 chacun, sur les deux versions de HA).

Vérification manuelle (27 octobre 2026) : le mainteneur a utilisé l’éditeur
sur HA 2025.12.5 (conteneur de développement) avec son domicile et le cloud
Intuis réels, dans le frontend HA, en suivant la liste de contrôle (dashboard,
modification et sauvegarde, garde-fous, redémarrage, mode autonome) ;
fonctionnement jugé correct.

Limites : les parcours automatisés utilisent un cloud et un cadre de dashboard
simulés ; la vérification réelle est manuelle et ponctuelle ; pas de détection
d’une modification simultanée depuis l’application Intuis avant l’envoi ; la
route ne répond pas à `HEAD` (405).
