# Dérogations et état climate

Les intentions de chauffage et l’état observé ont deux rôles distincts.
`OverrideManager` conserve le dictionnaire partagé des dérogations, y compris
lorsqu’il est vide. Le coordinateur et les entités climate utilisent cette même
interface pour créer, prolonger, retirer et sauvegarder les intentions. Les
commandes et prolongations d’une pièce sont sérialisées ; une ancienne expiration
ne peut pas effacer une nouvelle commande.

Le format persisté reste inchangé : `mode`, `temp`, `end`, `sticky`,
`last_reapply`, sous la clé de stockage `intuis_connect.overrides.<entry_id>`.
Les identifiants d’entités et les options existantes sont conservés. Les
sauvegardes capturent une copie des intentions avant leur sérialisation disque.

## Commande, confirmation et affichage

Après acceptation par l’API, climate présente un état en attente pendant au plus
**120 secondes**, indépendamment de la durée du preset (même hors-gel d’un an).
Cet état est marqué `assumed_state`. Le callback du véritable coordinateur lève
l’attente dès que le retour cloud confirme le mode et, lorsque nécessaire, la
consigne. La température affichée pendant cette attente est celle demandée.
Après confirmation, l’affichage suit à nouveau les données du coordinateur : la
fin d’un boost ou une modification dans l’application Intuis n’est pas masquée
par un ancien cache de mode HVAC ou de preset.

Une réponse cloud retardée peut conserver l’attente jusqu’à sa limite. La
minuterie locale lève ensuite l’attente et réécrit l’état sans exiger la réussite
d’un nouveau rafraîchissement. Une panne conserve la disponibilité héritée du
coordinateur : un ancien retour cloud n’est pas présenté comme fraîchement
confirmé. La durée de l’optimisme est bornée, pas celle de l’intention persistée.

Intuis peut représenter Away, Boost ou Hors-gel comme un mode manuel avec la
consigne correspondante. Une intention n’explique alors le preset affiché que si
elle est encore active et compatible avec le retour observé. Si le cloud fournit
une expiration positive, celle-ci doit correspondre à l’intention avec une
tolérance de **60 secondes** pour le transport et l’horloge. Une nouvelle
expiration distante ne reprend donc pas automatiquement l’ancien preset.
Sans mode explicite ni expiration, une modification externe ayant exactement la
même consigne reste indiscernable : l’interface ne peut pas inférer une information
absente du cloud. Le preset repose alors sur l’intention active compatible.

## Échecs et persistance

Une commande refusée ne crée ni intention, ni état en attente, ni minuterie.
Si l’API accepte la commande mais que la sauvegarde disque échoue, la commande a
bien été envoyée : son intention reste en mémoire et son affichage temporaire
reste visible, tandis que l’erreur de stockage remonte à l’appelant. Le succès
d’envoi ne garantit pas la persistance à travers un redémarrage après cette erreur.

En mode indéfini, le coordinateur prolonge l’intention avant expiration en
respectant l’intervalle minimal entre réapplications. Sans ce mode, il retire et
sauvegarde les intentions expirées au prochain rafraîchissement réussi.
L’affichage vérifie également l’expiration locale avant d’interpréter un preset.

## Minuteries et retrait des entités

Chaque entité possède au plus une minuterie d’attente et une minuterie de fin.
Une nouvelle commande remplace les anciennes ; une prolongation sticky
réactualise la minuterie de fin au prochain retour du coordinateur. Le retrait
normal de l’entité, notamment lors du déchargement ou rechargement de l’entrée,
annule les deux minuteries et désabonne son listener via le cycle de vie HA.

Si une requête réseau déjà envoyée termine après le retrait, elle peut encore
être acceptée par le cloud ; elle ne recrée cependant aucun état, minuterie ni
rafraîchissement pour l’entité retirée. Les commandes commencées après son retrait
sont refusées localement.

## Vérifications

Les tests de `test_heating_reconciliation.py` font passer les commandes par les
vraies entités climate, le mapping IntuisData, les callbacks DataUpdateCoordinator
et un Store HA dans un répertoire temporaire. Seuls le transport cloud et la
sortie graphique de l’entité sont simulés. Ils couvrent notamment stockage vide,
prolongation, expiration, recréation depuis le stockage, confirmation retardée,
modification externe, indisponibilité cloud, courses entre commandes et nettoyage
des minuteries. Aucun compte Intuis réel n’est utilisé.
