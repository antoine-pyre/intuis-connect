# Plan de fiabilisation Intuis Connect

Le plan suivant est distinct du socle de fiabilisation ci-dessous :
[intégration des apports des PRs et crédit des contributeurs](../docs/pr-integration-plan.md).
Il ajoute cinq changements, dont les 36 tâches sont réalisées et vérifiées localement.

Établi le **26 octobre 2026** à partir de la review globale du dépôt.
État : **61 tâches implémentées et validées ; les onze changements (socle et apports des PRs) sont archivés le 27 octobre 2026**.

## Organisation OpenSpec

Workflow `spec-driven` : `proposal.md` → `specs/` et `design.md` → `tasks.md`.
Chaque lot dispose de métadonnées `.openspec.yaml`, d’une proposition, d’un design,
de delta specs et de tâches numérotées. Les cases suivent l’implémentation effective et ses contrôles,
pas le seul travail de planification. Les contrats livrés figurent dans
`openspec/specs/` ; les changements archivés sont dans `openspec/changes/archive/`.

Format de référence : [schéma officiel spec-driven](https://openspec.dev/docs/schemas/spec-driven).

## Lots et suivi

| Changement | Priorité | Review | Tâches | Suivi |
|---|---|---|---:|---|
| [secure-energy-history-import](changes/archive/2026-10-27-secure-energy-history-import/proposal.md) | P1 | R1 | 10 | [Checklist](changes/archive/2026-10-27-secure-energy-history-import/tasks.md) |
| [reconcile-heating-overrides](changes/archive/2026-10-27-reconcile-heating-overrides/proposal.md) | P1/P2 | R2, R5 | 9 | [Checklist](changes/archive/2026-10-27-reconcile-heating-overrides/tasks.md) |
| [correct-schedule-mutations](changes/archive/2026-10-27-correct-schedule-mutations/proposal.md) | P1/P2 | R3, R7 | 10 | [Checklist](changes/archive/2026-10-27-correct-schedule-mutations/tasks.md) |
| [harden-api-and-energy-cache](changes/archive/2026-10-27-harden-api-and-energy-cache/proposal.md) | P1/P2 | R4, R8 | 10 | [Checklist](changes/archive/2026-10-27-harden-api-and-energy-cache/tasks.md) |
| [fix-multi-home-service-contracts](changes/archive/2026-10-27-fix-multi-home-service-contracts/proposal.md) | P2 | R6 | 10 | [Checklist](changes/archive/2026-10-27-fix-multi-home-service-contracts/tasks.md) |
| [strengthen-quality-workflow](changes/archive/2026-10-27-strengthen-quality-workflow/proposal.md) | P2/transverse | Q1, Q2, Q3 | 12 | [Checklist](changes/archive/2026-10-27-strengthen-quality-workflow/tasks.md) |

## Traçabilité de la review

| ID | Constat | Lot |
|---|---|---|
| R1 | Suppression des statistiques avant récupération, statuts trompeurs | secure-energy-history-import |
| R2 | Perte du dictionnaire partagé lorsque les dérogations sont vides | reconcile-heating-overrides |
| R3 | Transitions internes conservées lors d’un remplacement de plage | correct-schedule-mutations |
| R4 | URL complète, en-têtes et timeout perdus au retry 401 | harden-api-and-energy-cache |
| R5 | Mode HVAC/preset optimiste conservé indéfiniment | reconcile-heating-overrides |
| R6 | home_id refusé par les schémas et options figées sur le premier domicile | fix-multi-home-service-contracts |
| R7 | Températures de planning tronquées malgré un pas de 0,5 °C | correct-schedule-mutations |
| R8 | Erreurs énergétiques transformées en zéros et mises en cache | harden-api-and-energy-cache |
| Q1 | État métier dispersé et responsabilités trop concentrées | reconcile-heating-overrides ; strengthen-quality-workflow |
| Q2 | Duplications services/number et écriture dynamique de services.yaml | correct-schedule-mutations ; fix-multi-home-service-contracts ; strengthen-quality-workflow |
| Q3 | Tests de mocks, absence de Ruff en CI, environnement non reproductible | strengthen-quality-workflow et tests de chaque lot |

## Ordre d’exécution et dépendances

1. **Socle de validation** : groupe 1 de `strengthen-quality-workflow`.
   Il prépare l’environnement et les vrais points d’entrée sans imposer de refactoring global.
2. **Protection des données et commandes P1** : `harden-api-and-energy-cache`,
   puis `secure-energy-history-import`. L’import consomme le contrat de mesures
   défini dans le lot API ; il ne doit pas conserver un chemin qui assimile erreur et série vide.
3. **Chauffage et plannings** : `reconcile-heating-overrides`, puis
   `correct-schedule-mutations`. Ces lots partagent services.py et les fixtures avec
   les autres travaux : livrer des changements ciblés et éviter les réécritures simultanées.
4. **Multi-domicile** : `fix-multi-home-service-contracts` après les correctifs des handlers.
   Ce lot reprend leurs tests réels et stabilise l’enregistrement des services.
5. **Consolidation** : groupes 2 et 3 de `strengthen-quality-workflow`, après les cinq lots
   fonctionnels. Refactoriser seulement les comportements déjà protégés.

Les corrections P1 restent prioritaires : si le socle révèle une dette importante,
limiter son premier passage à ce qui rend les régressions exécutables et poursuivre
les correctifs. Chaque lot fonctionnel peut être une PR distincte ; le lot qualité
peut être livré en deux PR correspondant au socle et à la consolidation.

## Définition de terminé

- Les scénarios des specs sont couverts par des tests du code de production.
- Les tests ciblés et la suite complète passent dans les environnements supportés.
- Ruff et les checks CI configurés passent ; les résultats et limites sont consignés.
- Les identifiants d’entités, données persistées et automatisations compatibles sont préservés.
- Aucun compte Intuis ni équipement réel n’est nécessaire aux contrôles automatisés.
- La documentation des comportements et versions supportées est à jour.
- Les cases d’implémentation ne sont cochées qu’après réalisation et validation.
- Le changement est validé par OpenSpec, puis archivé seulement après livraison.

## Commandes de suivi

Depuis la racine, avec OpenSpec installé :

```sh
openspec list
openspec validate --all --strict
openspec status --change secure-energy-history-import
openspec instructions apply --change secure-energy-history-import
```

## Limites de la review initiale

La review initiale a analysé la syntaxe des 35 fichiers Python et reproduit cinq
cas sur du code extrait avec dépendances simulées. Elle n’a pas exécuté la suite
pytest complète ni Ruff, absents de l’environnement système. Ces contrôles sont
explicitement planifiés et ne doivent pas être présentés comme déjà réussis.

## Validation de cette planification

Le 26 octobre 2026, avec **OpenSpec 1.15.0** installé temporairement dans `/tmp`
(sans installation globale ni ajout aux dépendances du projet) :

- `openspec validate --all --strict` : **6 changements valides, 0 échec**.
- `openspec list --json` : **61 tâches détectées, 0 terminée**.
- Statut des artefacts : les six changements possèdent les quatre artefacts attendus.
- Vérification locale des liens Markdown, fichiers attendus et numéros de tâches : réussie.

Ces résultats valident les documents de planification ; ils ne valident pas encore
les corrections Python ni les tests d’implémentation futurs.

## Bilan d’implémentation locale

Les **61 tâches sur 61** des six changements sont cochées avec leurs preuves de
validation. Le socle puis les lots API/énergie, import sécurisé, chauffage,
plannings et multi-domicile ont été développés séquentiellement, relus et committés.
Le lot de consolidation final a également été relu et validé indépendamment avant commit.
Le [journal d’implémentation et de review](IMPLEMENTATION.md) trace chaque livraison.

La matrice finale exécute **334 tests sur chacune des deux versions HA**,
Ruff et les contrôles de dépendances. Les 345 cas du lot multi-domicile ont été
consolidés en retirant 20 assertions sans couverture produit supplémentaire et
en ajoutant 9 cas natifs/HTTP de compatibilité. OpenSpec strict valide les six
changements. Les limites de l’import et du cloud sont documentées dans les lots.

Les changements ne sont pas archivés : aucun push, déploiement, test cloud réel
ou exécution de CI distante n’est inclus dans cette validation locale.
