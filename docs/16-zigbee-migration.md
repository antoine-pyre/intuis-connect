# Dépréciation prévue et migration vers Zigbee2MQTT

La dépréciation de cette intégration cloud Intuis Connect est prévue. Pour les
radiateurs compatibles, la voie de migration retenue est le pilotage local par
Zigbee2MQTT et Home Assistant. Cette décision concerne la maintenance de cette
intégration communautaire. Aucune date de fin de support n'est fixée dans cette
annonce ; les installations existantes ne sont ni désactivées ni migrées
automatiquement.

Ce guide décrit le parcours utilisé le **11 novembre 2026** pour migrer quatre
radiateurs auparavant pilotés par Intuis Connect. Il distingue les résultats
constatés des manipulations qui dépendent du modèle et de son interface.

## 1. Vérifier la compatibilité

La migration a abouti avec des radiateurs **nativ / Intuis 3.0**, mis à jour vers
la version logicielle **3.0.8**, reconnus par Zigbee2MQTT comme `intuisradiator`.
Le réglage des consignes des quatre appareils a ensuite été vérifié dans HA.

La [fiche Zigbee2MQTT du modèle](https://www.zigbee2mqtt.io/devices/intuisradiator.html)
identifie cette famille. Le support Enki recommande également le logiciel
3.0.8 pour ses radiateurs Noirot nativ et indique la possibilité de mise à jour
avec Intuis Compagnon. Ce prérequis Enki est une information complémentaire,
pas une garantie de compatibilité Zigbee2MQTT de tous les appareils : voir
[la procédure du fabricant de la passerelle Enki](https://support.enki-home.com/hc/fr/articles/27481003987346-R%C3%A9initialiser-votre-objet-Noirot-Radiateur-s%C3%A8che-serviette).

Avant de commencer, relever la référence du radiateur, son type de thermostat,
sa version logicielle et la présence d'un éventuel module additionnel. La version
du logiciel du radiateur doit être distinguée de celle de l'application mobile
ou de la passerelle.

L'utilisation actuelle de l'application Intuis Connect ne suffit pas à déterminer
la compatibilité. Les anciens modules Muller/Netatmo « Intuitiv », les appareils
fil pilote et les chauffe-eau gérés par cette intégration n'ont pas été validés
par cette migration. Pour ces équipements, conserver le fonctionnement existant
tant qu'une solution locale adaptée n'a pas été vérifiée.

## 2. Exporter avant de déconnecter le premier radiateur

Cette étape doit précéder les réinitialisations et changements de réseau : un
appareil retiré d'Intuis peut ne plus apparaître dans les données exportées.

1. Faire une sauvegarde Home Assistant et conserver la configuration des
   automatisations et dashboards qui utilisent Intuis.
2. Installer une version de l'intégration contenant l'export complet des
   plannings, disponible dans la beta 2.1.0, puis redémarrer HA.
3. Vérifier que l'intégration communique encore avec Intuis et appeler
   `intuis_connect.refresh_schedules` pour actualiser les données chargées.
4. Depuis **Paramètres → Appareils et services → Intuis Connect**, télécharger
   les diagnostics de l'entrée d'intégration.
5. Ouvrir le JSON et rechercher `data.planning_export`. Vérifier les pièces et
   **tous les plannings, actifs comme inactifs**, leurs zones et températures.
   Un ancien diagnostic contenant seulement des informations de configuration
   ou des compteurs de plannings ne suffit pas.
6. Garder une copie des réglages Absent/Hors-gel, des exceptions de semaine,
   des automatismes tarifaires et des éventuels historiques souhaités.

L'export conserve les noms des pièces et des zones pour reconstruire leur
correspondance avec les futurs appareils Zigbee. Il contient les modèles déjà
chargés, pas une sauvegarde intégrale du compte ni un installateur de plannings
HA. Les séries historiques d'énergie et les automatisations HA n'y figurent pas.
Les noms et habitudes de chauffe peuvent être personnels : conserver le fichier
hors d'un dépôt public. Voir [le format détaillé des diagnostics](14-diagnostics.md).

## 3. Préparer le réseau local

Il faut disposer de :

- Home Assistant et son intégration **MQTT** ;
- un broker MQTT local, par exemple Mosquitto ;
- un coordinateur Zigbee dédié à Zigbee2MQTT et un réseau opérationnel ;
- une version de Zigbee2MQTT qui prend en charge `intuisradiator` ;
- la découverte Home Assistant activée dans Zigbee2MQTT.

Dans la configuration Zigbee2MQTT, la découverte utilise notamment :

```yaml
homeassistant:
  enabled: true
```

HA et Zigbee2MQTT doivent utiliser le même broker. Suivre
[la documentation d'intégration MQTT discovery](https://www.zigbee2mqtt.io/guide/usage/integrations/home_assistant.html).
Un même coordinateur ne peut pas être utilisé simultanément par ZHA et
Zigbee2MQTT. Le parcours documenté ici utilise Zigbee2MQTT ; ZHA n'a pas été testé.

## 4. Mettre à jour, puis appairer un radiateur à la fois

1. Vérifier la version sur le radiateur et effectuer la mise à jour si nécessaire,
   avant de quitter l'installation Intuis. Sur la famille nativ concernée,
   **Intuis Compagnon** installe le logiciel du radiateur par Bluetooth. Le menu
   de mise à jour « normal » ne propose que la dernière version **compatible avec
   la révision matérielle** du radiateur ; le choix d'une version précise passe
   par le **menu avancé**, protégé par un code d'accès. Le firmware est lié à la
   variante matérielle : un radiateur ne se voit proposer que les versions
   compilées pour son matériel. Dans notre migration, trois radiateurs ont pu
   passer en **3.0.8**, tandis qu'un quatrième, d'une variante différente, ne
   proposait que des versions **2.0.x**, où il fonctionne également ; une version
   logicielle antérieure n'est donc pas, en soi, une preuve d'incompatibilité.
   Vérifier la version effectivement installée après coup. La récupération du
   code du menu avancé, depuis l'application installée sur son propre téléphone,
   est décrite dans [le firmware et le menu avancé](17-firmware-menu-avance.md).
2. Ouvrir Zigbee2MQTT, prêt à activer **Permit join / Autoriser l'appairage**,
   mais le **laisser désactivé** pour l'instant.
3. Sur le radiateur, lui faire quitter son ancien réseau, puis ouvrir ses
   **Réglages** et lancer la **connexion à un réseau**. Le radiateur recherche,
   ne trouve aucun réseau et demande d'en **sélectionner** un : choisir
   **« Intuis 3.0 »**, et **seulement à ce moment** activer le Permit join dans
   Zigbee2MQTT. Le radiateur rejoint alors le réseau en mode Intuis 3.0. Les
   libellés exacts des menus varient avec le modèle et le logiciel : utiliser
   sa notice.

   Ce choix de réseau est déterminant. Avec un autre mode, l'interview
   Zigbee2MQTT **réussit quand même**, mais le radiateur remonte ensuite
   `local_temperature` à 0, reste en `idle`, n'incrémente pas l'énergie et garde
   la présence bloquée à `true` — un symptôme décrit dans
   [Koenkk/zigbee2mqtt#33183](https://github.com/Koenkk/zigbee2mqtt/issues/33183).
   Si un radiateur a déjà été appairé autrement, le retirer de Zigbee2MQTT, lui
   faire quitter son réseau, puis recommencer en sélectionnant « Intuis 3.0 ».
   Cette procédure d'appairage a aussi été ajoutée à la fiche du modèle en amont
   ([Koenkk/zigbee2mqtt.io#5733](https://github.com/Koenkk/zigbee2mqtt.io/pull/5733)).
4. Attendre la découverte et la fin de l'**interview** Zigbee2MQTT. Vérifier que
   l'appareil est identifié comme **Intuis `intuisradiator`**, puis que sa
   configuration aboutit.
5. Lui donner un nom stable, par exemple `radiateur_salon`, et fermer
   l'autorisation d'appairage une fois l'opération terminée.
6. Vérifier ses commandes et son retour d'état avant de passer au suivant.

Le [menu Connectivité décrit par Intuis](https://intuis.fr/sav/radiateurs-electriques/utiliser-et-regler/interface-de-pilotage-nativ-la-connectivite)
peut rechercher et rejoindre automatiquement un réseau Intuis existant.
Si l'appareil retourne dans l'ancienne installation, vérifier cette situation
plutôt que de conclure à une incompatibilité Zigbee. Conserver les moyens de
mettre à jour les appareils restants pendant la migration.

Un appareil Zigbee appartient à un seul réseau à la fois. Pour changer de
coordinateur, il faut lui faire quitter son ancien réseau selon sa notice ;
une réinitialisation peut être nécessaire. Un **Reset usine** efface aussi des
réglages : le réserver au parcours prévu pour le modèle et avoir sauvegardé
ce qui doit être reproduit. Voir [les contraintes Zigbee2MQTT](https://www.zigbee2mqtt.io/guide/faq/).

## 5. Valider les commandes locales

Dans **Exposes** de Zigbee2MQTT, vérifier au minimum la température mesurée,
la consigne, le mode `heat`/`off` et l'état de chauffe. Modifier une consigne
et vérifier son effet sur le radiateur, puis vérifier qu'un réglage local est
remonté. Une interview réussie seule ne prouve pas que les commandes fonctionnent.

La définition du modèle expose aussi une consigne d'inoccupation, le verrouillage
du clavier, l'unité de température, l'énergie et la présence. Leur présence dans
l'interface ne garantit pas que chaque mesure ou automatisme est exploitable sur
tous les firmwares. L'énergie, la présence et les fonctions de fenêtre ouverte
doivent être vérifiées séparément sur l'installation.

**Remontée spontanée et configuration Zigbee2MQTT.** Sur certains modules, la
configuration automatique de Zigbee2MQTT échoue sur le compteur d'énergie : le
convertisseur demande le reporting de l'attribut `status` (cluster `seMetering`),
que le module refuse (`UNREPORTABLE_ATTRIBUTE`). Zigbee2MQTT enchaîne les étapes
de configuration sans les isoler, si bien que tout ce qui suit cet échec — dont
la présence — n'est jamais configuré, et le radiateur ne remonte plus rien de
lui-même : ses valeurs ne changent qu'après un *refresh* manuel. Un
**Reconfigure**, sur la page de l'appareil dans Zigbee2MQTT, rétablit la
remontée : le bind et le reporting du thermostat, qui précèdent l'étape en échec,
aboutissent, et les valeurs reviennent ensuite toutes les dizaines de secondes.
Le correctif de fond, qui retire cette demande de reporting inutile, a été proposé
en amont : [issue Koenkk/zigbee2mqtt#33709](https://github.com/Koenkk/zigbee2mqtt/issues/33709)
et [PR Koenkk/zigbee-herdsman-converters#13831](https://github.com/Koenkk/zigbee-herdsman-converters/pull/13831).

**Échelle de l'énergie.** Tant que Zigbee2MQTT n'a pas lu le diviseur du compteur,
`energy_1` peut remonter des **Wh** présentés comme des kWh, soit une valeur de
l'ordre de plusieurs centaines de milliers. Le Reconfigure ci-dessus lit ce
diviseur et la valeur repasse en vrais kWh. Après ce changement d'échelle, un
ré-appairage ou un Reconfigure provoque un saut de la valeur cumulée, que le
tableau Énergie interprète comme une consommation : les statistiques concernées
peuvent être corrigées avec l'action `recorder.adjust_sum_statistics`.

Pour un appareil nommé `radiateur_salon`, la commande MQTT documentée utilise
l'endpoint `1` :

```text
Topic : zigbee2mqtt/radiateur_salon/set
Payload : {"system_mode_1":"heat","occupied_heating_setpoint_1":19.5}
```

La consigne documentée va de 7 à 28 °C. Voir
[les propriétés MQTT du modèle](https://www.zigbee2mqtt.io/devices/intuisradiator.html).
Dans HA, la découverte MQTT doit créer une nouvelle entité `climate`. Relever
son identifiant réel : le suffixe et le nom ne sont pas universels. Un appel
de validation, en remplaçant l'entité, peut être :

```yaml
action: climate.set_temperature
target:
  entity_id: climate.radiateur_salon_1
data:
  hvac_mode: heat
  temperature: 19.5
```

La chaîne de pilotage devient **HA → broker MQTT local → Zigbee2MQTT →
coordinateur Zigbee → radiateur**. HomeKit, un appareil Apple, une interception
TLS ou le serveur Intuis ne sont pas nécessaires au pilotage ainsi migré.
Cela ne signifie pas qu'une ancienne passerelle Wi-Fi laissée allumée a été
déconnectée d'Internet ; son éventuel retrait est une opération distincte.

## 6. Reconstruire les plannings dans Home Assistant

Les anciens plannings cloud ne sont pas transférés automatiquement dans les
radiateurs. Dans le fonctionnement utilisé ici, **HA exécute les horaires** et
envoie les consignes aux appareils.

1. Créer un helper **Planning / Schedule** par profil de chauffe depuis
   **Paramètres → Appareils et services → Entrées / Helpers**. Les helpers créés
   depuis l'interface restent modifiables depuis cette interface.
2. Reproduire les plages des sept jours depuis l'export, y compris les exceptions
   du week-end. Les `m_offset` comptent les minutes depuis lundi 00:00 ; la zone
   active peut commencer la semaine précédente. Respecter le fuseau du logement,
   la continuité dimanche/lundi et les passages à minuit.
3. Ajouter à **chaque plage** les températures de toutes les pièces comme données
   supplémentaires, avec des clés stables. Exemple de données d'une plage :

   ```yaml
   salon: 19
   chambre: 18
   bureau: 20
   cuisine: 18
   ```

4. Couvrir toute la journée avec des plages contiguës si une consigne doit
   toujours être définie. Contrôler le planning à chaque transition : une zone
   tarifaire ou un ordre fil pilote de l'export n'est pas une température.
5. Créer un `input_select` pour sélectionner le profil actif et une automatisation
   qui lit les attributs du `schedule` sélectionné, puis appelle
   `climate.set_temperature` sur les nouvelles entités MQTT.
6. Déclencher cette application lors du changement de profil, des changements
   de plage **ou de données du planning**, au démarrage de HA et à la reconnexion
   d'un radiateur. Un planning couvert toute la journée peut rester `on` quand
   ses températures changent : surveiller uniquement `on`/`off` serait insuffisant.

Les températures supplémentaires deviennent des attributs du helper pendant la
plage active. La [documentation HA des plannings](https://www.home-assistant.io/integrations/schedule/)
explique l'édition et les transitions entre plages contiguës.

Dans un dashboard, afficher le sélecteur, le mode réellement appliqué, les
températures prévues et celles des radiateurs. Une sous-vue de chauffe peut
donner accès à l'éditeur des helpers ; l'ancien éditeur fourni par cette
intégration continue de travailler sur les plannings Intuis, pas sur ces helpers.

## 7. Adapter les automatismes et les priorités

Remplacer les références cloud dans les automatisations, scripts et dashboards :

| Ancienne fonction | Remplacement local |
|---|---|
| `intuis_connect.switch_schedule` | `input_select.select_option` sur le sélecteur HA |
| `select.intuis_home_active_schedule` ou équivalent | Nouveau `input_select` |
| Anciens `climate` Intuis | Nouveaux `climate` créés par MQTT |
| Capteurs de présence Intuis | Capteurs locaux vérifiés, regroupés si nécessaire |
| Éditeur/calendriers cloud | Helpers `schedule` et dashboard local |

Exemple de sélection d'un profil local :

```yaml
action: input_select.select_option
target:
  entity_id: input_select.chauffage_planning_actif
data:
  option: Rouge
```

Dans notre installation, la sélection Tempo existante a été conservée : choix
du profil à 22 h selon la couleur du lendemain, puis vérification à 22 h 05.
Les actions utilisent désormais les helpers locaux. Les noms des profils,
capteurs de tarif et heures de bascule doivent être adaptés à chaque logement.

Les fonctions suivantes ont été reconstruites séparément dans HA ; elles ne
sont pas installées par cette intégration ni par ce guide :

- présence globale : groupe des détecteurs locaux, complété par les téléphones ;
- après 12 h sans présence confirmée : consignes du planning diminuées de 2 °C,
  notification au téléphone, puis reprise au retour ; horodatage persistant ;
- vacances : 10 °C prioritaires sur les horaires et le profil Tempo ;
- vacances automatiques : activation quand les deux personnes sont à plus de
  50 km à vol d'oiseau du domicile, désactivation dès qu'une revient à moins de
  50 km ; demande automatique distincte du mode manuel pour préserver sa priorité.

Une position inconnue ne doit pas être interprétée comme un retour. Le contrôle
géographique dépend des positions que les téléphones transmettent à HA.
Conserver des garde-fous pour les états inconnus et distinguer le mode demandé
de la consigne effectivement confirmée par l'appareil.

Définir les priorités dans le contrôleur commun : **vacances → absence prolongée
→ planning**. Les dérogations manuelles temporisées, l'anticipation de chauffe,
les alertes de fenêtre et le suivi des coûts ne sont pas reproduits par le seul
appairage Zigbee. Les fonctions internes du radiateur doivent être testées avant
de décider de les remplacer par des automatismes HA.

## 8. Terminer la bascule et conserver une possibilité de reprise

Avant de retirer l'intégration cloud, vérifier les consignes et retours d'état
des appareils, chaque profil, une transition d'horaire, les modes prioritaires
et leur sortie, ainsi que le redémarrage de HA et la reconnexion d'un appareil.
Effectuer aussi un essai sans accès Internet, en gardant le réseau local et les
services HA/MQTT/Zigbee2MQTT actifs.

La migration décrite a vérifié les commandes des quatre radiateurs, la
reproduction des trois profils de chauffe et la priorité des vacances à 10 °C,
y compris pendant un changement de profil. Les règles d'absence et de distance
ont été contrôlées par leurs calculs et des essais de commande ; cela ne constitue
pas un essai de 12 h d'absence réelle ou d'un déplacement réel à 50 km. Les essais
de coupure Internet et de panne complète restent à réaliser sur chaque installation.

Si HA, le broker, Zigbee2MQTT ou le réseau radio est indisponible, les prochaines
consignes ne peuvent plus être envoyées. Tester le comportement autonome du
radiateur et sa dernière consigne en cas de panne, plutôt que de supposer qu'il
conserve un planning local complet. Sauvegarder HA et les données du réseau
Zigbee2MQTT, dont la configuration et la sauvegarde du coordinateur.

Après validation, désactiver les automatismes cloud devenus inutiles, remplacer
les cartes restantes puis retirer l'intégration si aucun autre appareil n'en
dépend. Garder les exports et l'historique utile ; les nouveaux capteurs MQTT
ne reprennent pas automatiquement les anciennes statistiques d'énergie.

Un retour vers Intuis implique de suivre la procédure de réassociation du modèle
à l'ancien réseau. Ce n'est pas un simple changement de sélecteur dans HA :
conserver les informations et équipements nécessaires avant de les retirer.
