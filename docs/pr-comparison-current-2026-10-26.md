# Confrontation de toutes les PRs à l’état actuel du projet

Date : 26 octobre 2026. Référence locale : branche `codex/reliability-fixes`,
commit `f92e3e4`. Les résultats portent sur cette branche locale et non sur
la dernière release publiée ou uniquement sur le main distant.

## Conclusion

Les anciennes PRs de correction n’appellent plus de reprise globale.
Les fonctions principales encore absentes sont les statistiques et l’historique
horaires, les coûts, l’éditeur HTML et certaines extensions de l’édition des plannings.
Les PRs #22 et #24 ont donc encore une valeur fonctionnelle réelle ; leur
implémentation doit être adaptée au socle actuel plutôt que substituée à celui-ci.

## Inventaire exhaustif du dépôt

Recherche GitHub toutes situations confondues : 10 PRs, dont 4 fusionnées,
4 fermées sans fusion et 2 ouvertes. Les états ci-dessous viennent des
métadonnées de chaque PR, pas d’une déduction à partir de son titre.

| PR | État GitHub | Apport proposé | Confrontation au code actuel | Décision |
|---|---|---|---|---|
| [#2 — Fix repo url](https://github.com/antoine-pyre/intuis-connect/pull/2) | Fermée, non fusionnée | Corriger l’URL d’installation manuelle | Le README donne déjà intuis-connect pour l’installation manuelle. Le badge release et le bouton HACS conservent toutefois homeassistant-intuis-connect : reste documentaire distinct | Ne pas rouvrir la PR ; prévoir l’harmonisation des liens |
| [#5 — Températures par défaut](https://github.com/antoine-pyre/intuis-connect/pull/5) | Fermée, non fusionnée | Éviter un crash sur champs absents en remplaçant les températures par 1 | Le modèle préserve une consigne absente comme None, supporte therm_setpoint_fp dans les plannings et ignore des entrées malformées. Cela couvre le besoin de parsing sans inventer 1 °C | Ne pas reprendre le patch ; cela ne constitue pas un support complet FP4 |
| [#11 — Aqua Manager / event](https://github.com/antoine-pyre/intuis-connect/pull/11) | Fusionnée | Parser les plannings événementiels sans empêcher le démarrage | IntuisEventSchedule et IntuisEventZone existent, avec parsing défensif et tests | Déjà acquis ; le pilotage complet du chauffe-eau n’était pas l’objet de cette PR |
| [#12 — State class température](https://github.com/antoine-pyre/intuis-connect/pull/12) | Fusionnée | Permettre les statistiques du capteur température | IntuisTemperatureSensor utilise déjà MEASUREMENT | Déjà acquis |
| [#13 — Actualisation des capteurs](https://github.com/antoine-pyre/intuis-connect/pull/13) | Fusionnée | Lire les nouveaux objets room reconstruits par le coordinateur | _get_room et _handle_coordinator_update sont présents. L’énergie ajoute maintenant des règles de disponibilité et de fraîcheur | Déjà acquis, avec évolution du suivi énergétique |
| [#15 — Hors-gel, modes et chauffage](https://github.com/antoine-pyre/intuis-connect/pull/15) | Fusionnée | Hors-gel, presets natifs HA, boost, détection chauffage et compteur de minutes | Presets home/away/boost/eco, mode hg, seuil 0,5 °C, minutes flottantes et timestamp sont présents. La réconciliation des intentions et les timers ont été consolidés depuis | Conserver les acquis actuels ; la détection chauffage reste une estimation lorsqu’elle repose sur l’écart de température |
| [#16 — Workflows et correctifs](https://github.com/antoine-pyre/intuis-connect/pull/16) | Fermée, non fusionnée | Cache CI plus changements climate/mapper proches de #15 | Le cache CI est configuré, avec contraintes et matrice HA 2024.6/2026.10. Les fonctions climate sont déjà présentes, sans la troncature des minutes du patch | Dépassée par #15 et les changements récents |
| [#17 — Hourly energy and calendar](https://github.com/antoine-pyre/intuis-connect/pull/17) | Fermée, non fusionnée | Première proposition énergie horaire et planning HTML | Les calendriers existent déjà ; les fonctions horaires et HTML restent absentes. L’auteur a indiqué que la PR était remplacée | Référence historique ; travailler à partir de #22/#24 |
| [#22 — Énergie horaire, coûts et HTML](https://github.com/antoine-pyre/intuis-connect/pull/22) | Ouverte | Statistiques horaires, import horaire, coûts, services et éditeur HTML | Plusieurs nouveautés réelles, mais réécriture d’imports, capteurs et services désormais consolidés localement | Extraire et adapter par fonctionnalités |
| [#24 — Planning et installation HTML](https://github.com/antoine-pyre/intuis-connect/pull/24) | Ouverte | Une grande partie de #22, route HTTP, corrections et réglages planning | Le backend énergie/coût est identique à #22 ; les différences utiles concernent surtout le planning et sa distribution | Évaluer son supplément à #22 ; ne pas compter deux fois le même apport |

## Ce que #22 ajoute réellement, fonction par fonction

| Fonction | État actuel | Proposition #22 | Valeur résiduelle / reprise |
|---|---|---|---|
| Lecture énergétique avec scale 1hour | La granularité existe dans les options et les lectures live | Nouvelle méthode API renvoyant une série de points horaires | Nouveau contrat de série, à ajouter au parseur strict actuel |
| Statistiques horaires recorder | Pas d’updater dédié ; les états du capteur journalier alimentent le recorder | Écriture directe de points kWh par heure, périodique | Nouveauté principale ; sélectionner 1hour actuellement ne reconstitue pas à lui seul l’historique horaire exact |
| Historique jusqu’à 730 jours | Déjà présent en valeurs quotidiennes, sur jours locaux clos | Import horaire ou quotidien avec requêtes découpées | Seule la granularité horaire et son découpage sont nouveaux ; préserver validation, transactions, acquittements et annulation actuels |
| Coûts par pièce | Absents | Capteur coût, tarif fixe ou entité HA, historique de prix, statistiques et recalcul | Nouveau chantier, distinct des kWh |
| Sens du capteur énergie | Maximum journalier, TOTAL_INCREASING, fraîcheur et disponibilité explicites | Cumul historique + consommation du jour, sans state_class, import horaire comme writer principal | Changement de contrat visible pour cartes et automatisations ; ne pas l’introduire implicitement |
| Total énergétique domicile | Agrégat journalier tenant compte des pièces inconnues ou périmées | Agrégat cumulatif destiné à l’affichage, retrait de state_class | Pas une nouvelle capacité d’agrégation ; changement de sens et régression possible de suivi |
| Éditeur HTML | Carte Lovelace externe et services existants ; aucun HTML embarqué | Grille semaine, créneaux, zones, sélection du planning, sauvegarde et connexion HA/REST | Interface supplémentaire réelle, indépendante de l’énergie |
| Sauvegarde du planning complet | La méthode API async_sync_schedule existe ; aucun service public sync_schedule | Nouveau service public acceptant le timetable complet | Nouveau point d’entrée ; réutiliser les verrous et modèles courants de schedule_mutations |
| Édition des créneaux d’un planning inactif | set_schedule_slot vise le planning actif ; set_zone_temperature accepte déjà un planning nommé | Ciblage du planning par nom ou ID dans les gestionnaires | Extension utile pour les créneaux ; ne pas présenter l’édition des températures d’un planning nommé comme nouvelle |
| Demi-degrés et concurrence | Déjà gérés et testés par services et number via schedule_mutations | Les anciens chemins de mutation sont modifiés séparément | Préserver le chemin local partagé, sans reprendre la troncature int(value) de la PR |
| Normalisation hebdomadaire | Remplacement cyclique d’intervalle, restauration finale et validation des bornes/offsets | normalize_timetable et déduplication d’offsets | Ne pas substituer une normalisation tolérante à la validation actuelle ; une sauvegarde complète devra aussi être validée |
| Noms après renommage | Le service résout les noms courants ; les libellés du calendrier et du device number sont mémorisés | Noms calendrier/device number relus depuis le planning courant | Petit apport encore utile et isolable |
| Données UI des plannings | Capteurs summary, zones, IDs et weekly_timetable déjà présents | room_names, index des plannings et classe supplémentaire de capteur individuel | room_names/index peuvent aider l’UI ; éviter la multiplication des représentations et entités |
| Refresh à expiration climate | Timers annulés/remplacés, retrait pris en compte, état optimiste borné | Changement du callback vers async_create_task | Besoin déjà pris en charge autrement ; conserver le cycle de vie local |
| Debug des modules | Logs et modèles existants | Logs supplémentaires sur radiator_state | Pas de nouvelle fonction utilisateur ; n’ajouter que ce qui manque au diagnostic |
| Options / traductions | Configuration existante, services statiques et traduction des champs | Options horaires et coûts, traductions supplémentaires | Reprendre uniquement les nouveaux réglages, avec sélecteurs valides et comportement par défaut explicite |

### Éléments du socle local à préserver

- Retry HTTP 401 fidèle et borné, erreurs énergétiques typées, distinction entre
  zéro mesuré et mesure indisponible.
- Cache par pièce, jour du domicile, conservation de la fraîcheur des dernières
  mesures et agrégats incomplets explicites.
- Remplacement historique transactionnel acquitté par le worker recorder,
  baseline live conservée, idempotence et drain pendant unload.
- Intentions de chauffage partagées et réconciliées ; timers gérés au retrait.
- Mutations de planning sous verrou, copie avant commande, publication après
  succès, restauration de fin d’intervalle et températures par demi-degré.
- Services statiques, validation sur les modèles courants, ciblage home_id,
  cycle de vie après ajout/retrait d’entrées.
- Tests natifs, sockets externes interdites, contraintes reproductibles et minimum
  HA 2024.6.

Les PRs ouvertes ne fournissent pas ces garanties au niveau du socle actuel.
Leur application globale pourrait les contourner ou les réintroduire sous une
forme ancienne, même si GitHub les déclare fusionnables avec main.

## Ce que #24 apporte en plus de #22

Les branches ont divergé : 23 commits en avance et 1 en retard dans la comparaison
#22 vers #24. Parmi leurs 20 chemins communs, **15 fichiers ont un contenu
strictement identique**, notamment l’API, les statistiques horaires, les coûts,
l’import, le config flow et les traductions.

| Différence #24 | Situation actuelle / décision |
|---|---|
| HTML déplacé dans resources et servi à /api/intuis_connect/planning | Absent ; bon complément d’installation si l’éditeur HTML est adopté |
| Dépendance http et ETag lié au manifest | Nécessaires à évaluer avec cette route ; le bump 2.0.1 ne constitue pas un apport métier |
| away_temp et hg_temp transmis par sync_schedule | Le backend sait déjà envoyer ces champs mais aucun service ne permet de modifier ces températures de planning ; nouvelle capacité utile à intégrer sous verrou |
| Ajustements HTML des horaires et de la sauvegarde | À conserver comme matériau du frontend ; vérifier contre les vrais contrats de services actuels |
| Itération sur list(hass.data[DOMAIN].items()) | Objectif déjà couvert par les snapshots de service_targets et les gardes de chargement |
| Retour des sept jours dans IntuisIndividualScheduleSensor | La correction porte sur une classe ajoutée qui n’est pas instanciée par le setup inspecté. Le summary effectivement créé filtre encore les jours sans transition ; reprendre le besoin dans le vrai producteur consommé par l’UI |
| Changements du fuseau dans intuis_data | Le socle actuel gère déjà le fuseau et le cache par pièce ; ne pas remplacer ce mécanisme par la variante des PRs |
| Surcharge de températures copiée dans set_schedule_slot | Défaut confirmé : variables non définies ; ne pas reprendre cette portion |

## Petits apports possibles avant les gros chantiers

1. Actualiser les noms de calendriers et de devices number après renommage du
   planning, en conservant les IDs et en testant le comportement du registry.
2. Exposer les noms de pièces avec les données de planning si le frontend en a
   besoin ; enrichir les summaries existants.
3. Ajouter le ciblage d’un planning non actif à set_schedule_slot, en conservant
   le planning actif comme défaut pour les automatisations existantes.
4. Étendre le chemin de mutation commun pour les températures away/hg et pour
   un timetable complet, avec validation et publication après succès.
5. Harmoniser les liens de dépôt du README ; ce reliquat ne nécessite aucune
   reprise de l’ancienne branche #2.

Ces points sont petits et cohérents avec l’existant. Ils ne sont pas tous des
correctifs déjà prêts à copier : ils nécessitent leurs validations adaptées.

## Chantiers fonctionnels restants

| Ordre | Lot | Critère de réussite |
|---|---|---|
| 1 | Backend énergie horaire, inspiré de #22 | Série stricte et dédupliquée, heures closes, continuité recorder, reprise après arrêt, aucune perte des garanties multi-domicile et quotidiennes |
| 2 | Coûts, inspirés de #22 | Prix historique explicite, cohérence de devise, sélecteurs valides, statistiques idempotentes, migrations sans suppression d’entités étrangères |
| 3 | Services de planning étendus | Cible non active, timetable complet, températures away/hg via le même verrou et le même contrat de publication |
| 4 | Frontend planning et distribution #24 | Sauvegarde correspondant aux nouveaux services, noms rendus comme texte, chargement/reconnexion et multi-domicile vérifiés |

Les lots 1 et 3 sont indépendants fonctionnellement : le planning n’exige pas
les coûts ou l’énergie horaire pour être livré.

## Vérifications et limites de la confrontation

- PRs relues aux commits #22 `3174384d9222bdca5310721940ece95fe6d1fce6`
  et #24 `fb39b93c1eaf2a498c7274210b566864a2497669`.
- Métadonnées et diff des dix PRs consultés ; comparaison des fichiers #17/#22/#24.
- Code et documentation du socle local relus après le commit de consolidation.
- Nouvelle exécution sur ce socle : **334 tests réussis sur HA 2024.6.4 et
  334 sur HA 2026.10.4** ; Ruff passe.
- L’échec de registre mentionné dans la revue précédente n’est plus présent
  sur le commit actuel. Ces résultats remplacent l’ancien état de validation.
- Ces tests valident le socle actuel, pas une intégration des PRs qui n’a pas
  été effectuée. Les défauts concrets précédemment reproduits restent détaillés
  dans [la revue technique](pr-review-2026-10-26.md).
- Pas de fusion, de modification des PRs, de commande vers les radiateurs,
  de publication de release ou de test cloud réel.

Le fork communautaire #28 et la proposition fil pilote #27 ne sont pas des PRs
de ce dépôt ; ils ne sont pas comptés comme des contributions déjà fusionnables.
