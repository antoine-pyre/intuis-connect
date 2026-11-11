# Tasks

Priorité : **P2** — Review : **R6**.

Consulter proposal.md, design.md, specs/ et le [plan global](../../../README.md) avant implémentation. Les dix tâches ci-dessous sont implémentées et vérifiées sur les deux environnements HA.

## 1. Tests des vrais points d’entrée

- [x] 1.1 Enregistrer les vrais services dans un harness HA et les appeler via hass.services.async_call avec les schémas actifs.
- [x] 1.2 Tester home_id pour chaque service, deux domiciles avec noms identiques, cible inconnue et absence de commande sur l’autre domicile.
- [x] 1.3 Tester les défauts sans cible, le champ historique day, ajout/rechargement d’entrée et refresh des plannings.

## 2. Schémas, descriptions et cycle de vie

- [x] 2.1 Ajouter home_id optionnel dans les schémas et centraliser la résolution des entrées et les erreurs retournées à l’appelant.
- [x] 2.2 Remplacer les options de noms figées par des champs validés sur les données courantes du domicile ciblé.
- [x] 2.3 Retirer la génération de services.yaml et ses appels ; fournir des descriptions statiques cohérentes avec les schémas et traductions.
- [x] 2.4 Préserver les défauts sans cible et la compatibilité day/start_day/end_day ; documenter l’avertissement de choix implicite.
- [x] 2.5 Tester et corriger l’enregistrement/désenregistrement avec plusieurs entrées, y compris le retrait de la première et de la dernière.

## 3. Validation

- [x] 3.1 Vérifier setup et refresh avec répertoire du composant en lecture seule ; exécuter les tests services/multi-home puis la suite complète.
- [x] 3.2 Mettre à jour les exemples YAML et la documentation des paramètres et des sélecteurs.

## Validation — 26 octobre 2026

- **345 tests passent** sur HA 2024.6.4 / Python 3.12.14 et HA 2026.10.4 / Python 3.14.4.
- **46 nouveaux cas** dans `tests/unit/test_multi_home_services.py` appellent les services réellement enregistrés : cinq schémas home_id, deux domiciles/noms identiques, cibles inconnues ou vides, défauts sans cible, filtres de pièce validés avant création de tâche, nouveaux noms après refresh, ajout/rechargement et premier/dernier retrait, erreur de déchargement et acquittement tardif.
- Le test setup + refresh utilise le coordinateur et Store natifs et émule un composant en lecture seule ; seul le transport/API et le chargement des plateformes sont simulés. Le helper de bootstrap frame de HA récente est initialisé comme dans HA réel.
- Les champs YAML statiques et traductions FR/EN sont comparés aux schémas réellement enregistrés ; aucune liste de noms personnelle n’est générée à l’exécution.
- Ruff sur les deux environnements, OpenSpec strict (6/6) et `git diff --check` réussissent ; les tests interdisent les sockets externes.
- Le filtre room_name sans home_id cible les domiciles contenant cette pièce ; aucun match est une erreur avant création de tâche. Cette précision de compatibilité est documentée dans les specs/design et [docs/10-multi-home-services.md](../../../../docs/10-multi-home-services.md).
- Noms de services, identifiants d’entités, formats de stockage et minimum HA inchangés ; aucune opération vers un compte Intuis réel.
