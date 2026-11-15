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

Deux faits établis par l'analyse de l'application :

1. Les codes ne sont **pas** écrits en dur dans l'application. Elle est écrite en
   Flutter ; aucun code PIN n'est une constante du binaire.
2. L'application **télécharge** un fichier `config.json` (qui contient la liste
   des codes) depuis un serveur, puis **en garde une copie sur le téléphone**.

La procédure ci-dessous récupère cette copie locale — c'est-à-dire **ses propres
données, sur son propre appareil**. Elle ne touche à aucun serveur.

> **À propos de la « récupération depuis le serveur ».** L'application obtient ce
> `config.json` auprès d'un serveur tiers, à l'aide d'identifiants d'un compte de
> service inclus dans l'application. Cette voie n'est **pas** documentée ici : se
> connecter au serveur d'un tiers avec des identifiants extraits d'une
> application constitue un accès non autorisé à son système, quelle que soit
> l'intention. La méthode locale ci-dessous donne exactement le même fichier et
> les mêmes codes, sans ce problème.

## 3. Partie A (facultative) — Confirmer où sont les codes

Cette partie sert seulement à comprendre d'où viennent les codes. Pour les
récupérer directement, passer à la partie B.

Prérequis (macOS, Homebrew) :

```bash
brew install capstone ninja pkg-config
pip3 install --user pycryptodome
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
Android (`adb backup`), qui inclut les données de l'app tant que celle-ci
n'interdit pas la sauvegarde (c'est le cas d'Intuis Compagnon).

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

   Le script écrit `intuis_backup.tar` et extrait les fichiers. Le fichier
   recherché est :

   ```
   apps/com.muller.app_toolbox/r/app_flutter/config.json
   ```

3. Lire les codes dans `config.json`, clé `accessCodes`. Chaque entrée a un champ
   `pin` et une liste `features` (`DFU++`, `DFU-BETA`, `CONFIG`). Le code à saisir
   dans « Menu avancé → Mise à jour » est celui dont `features` contient `DFU++`.
   Les codes observés sont globaux (indépendants du modèle) et sans date
   d'expiration, mais chacun doit lire les siens dans son propre fichier.

## 5. Rappels

- Ces codes donnent accès au menu de mise à jour ; ils ne réparent rien en
  eux-mêmes. Si un radiateur a un défaut matériel (capteur), la mise à jour peut
  échouer ou ne pas corriger le problème.
- `config.json` contient aussi la liste des appareils connus de l'application :
  le conserver hors d'un dépôt public.
- Garder un moyen de mettre à jour les appareils restants pendant la migration,
  et vérifier la version effectivement installée après chaque mise à jour.
