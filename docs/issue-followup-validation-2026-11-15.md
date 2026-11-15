# Suivi des issues et PR — 15 novembre 2026

Le lot réunit les commits originaux des PR #37 (timer HA), #36 (pièces sans
mesure) et #39 (retour Zigbee), puis ajoute le correctif #38 et durcit le lecteur
de sauvegarde Android. Les sources et auteurs sont conservés dans l'historique
et CONTRIBUTORS.md.

## Vérifications exécutées

- HA 2024.6.4 / Python 3.12.15 : suite complète, 601 réussites et 2 tests de
  parité ignorés faute de Node dans le PATH initial. Les 2 tests ont ensuite
  réussi avec Node 22.14.0. Total : 603 réussites.
- HA 2026.10.4 / Python 3.14.4 : mêmes résultats, 603 réussites au total.
- Suite JavaScript `node --test tests/js/*.test.js` : réussite.
- Ruff : réussite. Dépendances : `pip check` sur le minimum et `uv pip check`
  sur la version courante, sans incompatibilité.
- Tests HA exécutés avec threads locaux autorisés et sockets externes interdits
  par pytest-socket. Transport cloud simulé ; aucune commande à du matériel.

Les régressions #38 utilisent le véritable coordinateur HA et le mapper :
configuration absente ou malformée, conservation de la dernière valeur valide,
premier démarrage sans configuration, fraîcheur des capteurs, évolution des
mesures de pièce et rétablissement. Les erreurs de requête restent propagées.

Le lecteur de sauvegarde est testé avec des archives synthétiques chiffrées ou
non, compressées ou non : mot de passe UTF-8, octets signés du checksum Android,
mauvais mot de passe/checksum, en-têtes invalides, refus des liens et chemins
inattendus, extraction du seul fichier attendu et refus d'écrasement.

## Limites et suivi

- Le terrain FP4 reste celui rapporté dans #27 ; le correctif énergétique #36
  attend une confirmation sur ces pièces réelles. L'agrégat quotidien n'est pas
  modifié par #36.
- Aucun téléphone Android ni sauvegarde réelle n'a été utilisé pour le script.
  Les limites d'adb backup sont documentées avec la source Android officielle.
- #31 reste en attente d'une confirmation de ciblage des plannings sur une
  copie de test. Le retour sur les dépréciations est positif.
- #33 reste le suivi du convertisseur de plannings, qui n'est pas développé
  par ce lot. Le choix de son interface est distinct de la migration Zigbee.
