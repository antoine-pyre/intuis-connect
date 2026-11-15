# Firmware des radiateurs et menu avancé d'Intuis Compagnon

La migration vers Zigbee2MQTT suppose souvent d'installer une version précise du
logiciel du radiateur (par exemple **3.0.8** sur la famille nativ / Intuis 3.0).
Ce document explique pourquoi une version donnée n'est pas toujours proposée, et
comment retrouver, **sur son propre téléphone**, le code que l'application
Intuis Compagnon demande pour son menu avancé.

Ce document décrit une **procédure**. Les codes eux-mêmes ne sont pas publiés
ici : chacun récupère les siens, sur son propre appareil, par la méthode
ci-dessous. Il reste de la responsabilité de chaque personne de décider ce
qu'elle fait sur son matériel.

## 1. Pourquoi un menu avancé

Dans Intuis Compagnon (paquet Android `com.muller.app_toolbox`), le menu de mise
à jour « normal » ne propose que la dernière version **stable compatible avec la
révision matérielle** du radiateur. Pour choisir une version précise, l'app a un
**menu avancé**, protégé par un code PIN. Les fonctionnalités protégées
observées sont :

- la **mise à jour** du firmware par le canal de production (`DFU++`) ;
- la mise à jour par le **canal beta** (`DFU-BETA`), parfois en avance sur la
  production ;
- un menu de **configuration** avancée de l'appareil (`CONFIG`).

`DFU` signifie *Device Firmware Update* : la mise à jour du logiciel interne du
radiateur, transmise par Bluetooth depuis le téléphone.

Un firmware est lié à une **révision matérielle** précise. Un radiateur d'une
variante donnée ne se verra proposer que les versions compilées pour cette
variante. C'est pourquoi certains appareils restent en branche **2.0.x** quand
d'autres passent en **3.x** : ce n'est pas un défaut de l'application, et une
version 2.0.x peut être parfaitement fonctionnelle.

## 2. Où sont les codes

Observations du contributeur sur la version de l'application analysée :

1. Les codes ne sont **pas** écrits en dur dans l'application. Elle est écrite en
   Flutter ; aucun code PIN n'est une constante du binaire.
2. L'application **télécharge** un fichier `config.json` (qui contient la liste
   des codes) depuis un serveur, puis **en garde une copie sur le téléphone**.

La procédure ci-dessous récupère cette copie locale — c'est-à-dire **ses propres
données, sur son propre appareil**. Elle ne touche à aucun serveur.

> Cette procédure porte uniquement sur une sauvegarde locale de son propre
> appareil. Elle ne documente ni connexion au serveur tiers ni utilisation
> d'identifiants de service extraits de l'application.

## 3. Partie A (facultative) — Confirmer où sont les codes

Cette partie sert seulement à comprendre d'où viennent les codes. Pour les
récupérer directement, passer à la partie B.

Prérequis (macOS, Homebrew) :

```bash
brew install capstone ninja pkg-config
python3 -m pip install cryptography
```

1. Récupérer l'APK installée depuis un téléphone Android en débogage USB :

   ```bash
   adb shell pm path com.muller.app_toolbox
   # copier base.apk et le split arm64 (il contient le code Dart)
   adb pull <chemin>/base.apk intuis_compagnon_base.apk
   adb pull <chemin>/split_config.arm64_v8a.apk intuis_compagnon_arm64.apk
   ```

2. Décompiler le code Dart (Flutter AOT) avec blutter :

   ```bash
   git clone --depth 1 https://github.com/worawit/blutter.git
   mkdir arm64 && unzip -o intuis_compagnon_arm64.apk -d arm64
   python3 blutter/blutter.py arm64/lib/arm64-v8a blutter_out
   ```

3. Lire la logique dans la sortie. Fichiers utiles :
   - `blutter_out/asm/app_toolbox/src/api/config.dart` : montre que l'app
     télécharge puis met en cache un `config.json` ;
   - `blutter_out/asm/app_toolbox/src/models/access_code.dart` : le modèle
     `AccessCode` (champs `pin`, `features`, `validFrom`, `validTo`) ;
   - `blutter_out/pp.txt` : le pool de constantes, où apparaissent les chaînes
     `accessCodes`, `DFU++`, `DFU-BETA`, `CONFIG`.

   Conclusion : le PIN est un `AccessCode` chargé depuis `config.json`, écrit sur
   le disque de l'app (`getApplicationDocumentsDirectory()` →
   `app_flutter/config.json`).

## 4. Partie B — Récupérer les codes (copie locale, sans root)

L'application n'est pas « debuggable » et le téléphone n'est pas rooté : on ne
peut pas lire directement le fichier de l'app. On passe par une sauvegarde
Android (`adb backup`), lorsque le téléphone et la version de l'application
autorisent encore l'export de ces données. Cette méthode est un retour
d'expérience, pas une garantie de compatibilité pour tous les téléphones.

**Limite Android.** À partir d'Android 12, les données des applications ciblant
l'API 31 ou plus sont exclues de `adb backup`, sauf application debuggable
([documentation Android](https://developer.android.com/about/versions/12/behavior-changes-12#adb-backup-restrictions)).
Une sauvegarde peut donc être créée sans le fichier recherché. Si le script
signale son absence, cette procédure ne permet pas de récupérer les codes sur
cette combinaison téléphone/application. Les versions exactes Android et
Intuis Compagnon du retour initial n'ont pas été précisées dans la PR #39.

Le script nécessite **Python 3.12+** et `cryptography` :

```bash
python3 -m pip install cryptography
```

Il accepte les en-têtes Android Backup versions 2 à 5, chiffrés en AES-256
ou non chiffrés. Les tests utilisent des sauvegardes synthétiques ; ils ne
valident pas la collecte sur un téléphone ni tous les anciens formats.

1. Téléphone Android en débogage USB, branché. Sauvegarder les données de l'app,
   **en choisissant un mot de passe de chiffrement sur le téléphone** :

   ```bash
   adb backup -f intuis_backup.ab -noapk -noshared com.muller.app_toolbox
   ```

   Sur le téléphone : écran « Sauvegarde complète » → saisir un mot de passe →
   « Sauvegarder mes données ».

2. Déchiffrer la sauvegarde avec le script fourni
   [`scripts/decrypt_intuis_backup.py`](../scripts/decrypt_intuis_backup.py). Le
   mot de passe est demandé de façon masquée, il ne transite pas par la ligne de
   commande :

   ```bash
   python3 scripts/decrypt_intuis_backup.py intuis_backup.ab
   ```

   Le script vérifie le padding et le checksum de la clé Android, puis écrit
   uniquement `intuis_backup_config.json`, sans afficher les codes. Il ne crée
   pas de copie TAR ni d'extraction des autres données de l'application et
   refuse d'écraser un fichier existant. Le chemin attendu dans la sauvegarde est :

   ```
   apps/com.muller.app_toolbox/r/app_flutter/config.json
   ```

3. Lire les codes dans `config.json`, clé `accessCodes`. Chaque entrée a un champ
   `pin` et une liste `features` (`DFU++`, `DFU-BETA`, `CONFIG`). Le code à saisir
   dans « Menu avancé → Mise à jour » est celui dont `features` contient `DFU++`.
   Le contributeur a observé des codes indépendants du modèle et sans date
   d'expiration dans son fichier ; cela ne garantit pas les valeurs ni les
   conditions d'accès des autres versions de l'application.

## 5. Rappels

- Ces codes donnent accès au menu de mise à jour ; ils ne réparent rien en
  eux-mêmes. Si un radiateur a un défaut matériel (capteur), la mise à jour peut
  échouer ou ne pas corriger le problème.
- `config.json` contient aussi la liste des appareils connus de l'application :
  le conserver hors d'un dépôt public.
- Garder un moyen de mettre à jour les appareils restants pendant la migration,
  et vérifier la version effectivement installée après chaque mise à jour.
