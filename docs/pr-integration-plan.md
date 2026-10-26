# Plan d’intégration des apports des PRs

Établi le 26 octobre 2026 sur `codex/reliability-fixes`, référence `f92e3e4`.
**État : en cours, 1/36 tâches réalisées et vérifiées.**
Les documents et le registre de crédits sont préparés ; aucune fonction Python,
frontend ou recorder de ces lots n’est implémentée par cette planification.

## Objectif et périmètre

Intégrer tous les apports fonctionnels utiles des dix PRs examinées, en conservant
les fonctions déjà intégrées, le crédit de leurs auteurs et les garanties du socle.
« Tous les éléments » signifie couvrir chaque besoin et amélioration des PRs :
pas recopier du code mort, des défauts connus ou des variantes remplacées.

Les fonctionnalités de #22/#24 restent à livrer sous forme adaptée. Le planning
et l’énergie sont indépendants. Le fil pilote de l’issue #27 et le fork de #28
ne sont pas automatiquement ajoutés au périmètre des PRs ; toute reprise de ces
sources devra être explicitement tracée.

Références : [confrontation des dix PRs](pr-comparison-current-2026-10-26.md),
[revue technique](pr-review-2026-10-26.md), [contributeurs](../CONTRIBUTORS.md)
et [socle de fiabilisation](../openspec/README.md).

## Lots OpenSpec et dépendances

| Ordre | Lot | Dépendances | Taille relative | Livraison |
|---|---|---|---|---|
| 1 | [Attribution et liens](../openspec/changes/preserve-contributor-attribution/proposal.md) | Aucune | Petite | Registre, mentions, URL et règles de provenance |
| 2A | [Services de planning étendus](../openspec/changes/extend-schedule-editing/proposal.md) | 1 et socle actuel | Moyenne | Planning inactif, sync complet, away/hg, renommages et summaries |
| 2B | [Énergie horaire](../openspec/changes/add-hourly-energy-statistics/proposal.md) | 1 et socle actuel | Grande | Série horaire, historique, updater et continuité recorder |
| 3A | [Planning HTML embarqué](../openspec/changes/add-bundled-planning-ui/proposal.md) | 2A | Moyenne à grande | UI intégrée/autonome, route HTTP, cache, authentification et crédit |
| 3B | [Coûts énergétiques](../openspec/changes/add-energy-cost-statistics/proposal.md) | 2B | Grande | Prix, séries/coûts, historique et recalcul |

Ordre séquentiel suggéré : **1 → 2A → 2B → 3B → 3A**. Les lettres A/B indiquent
les dépendances fonctionnelles indépendantes, pas une délégation automatique à des
agents. Chaque lot doit être reviewable séparément. Ne pas bloquer le planning
sur les coûts si une livraison indépendante est préférable. Les tailles ne sont
pas des estimations calendaires ; le prototype recorder conditionne l’effort du lot 2B.

## Traçabilité de toutes les PRs

| Source / auteur | Besoin | Disposition planifiée |
|---|---|---|
| #2 — tranb3r | Liens du dépôt | Lot 1 : harmoniser les liens restants ; ne pas rouvrir l’ancienne branche |
| #5 — halfred | Températures absentes | Conserver le parsing défensif actuel et ses tests ; créditer la proposition sans reprendre la valeur fictive 1 °C |
| #11 — chrislek | Plannings event/Aqua Manager | Déjà intégré ; conserver le parsing et les tests, sans annoncer un pilotage ECS complet |
| #12 — TheFab21 | State class température | Déjà intégré ; préserver MEASUREMENT |
| #13 — sremy91 | Capteurs actualisés | Déjà intégré ; préserver lectures courantes et fraîcheur énergétique |
| #15 — sremy91 | Hors-gel, presets, boost, chauffage/minutes | Déjà intégré ; préserver réconciliation actuelle et minutes flottantes |
| #16 — sremy91 | Workflows et changements climate connexes | Besoins couverts ; conserver matrice/contraintes et ne pas réintroduire la troncature des minutes |
| #17 — TheFab21 | Proposition initiale horaire et planning | Source historique des lots 2A/2B/3A ; #22/#24 servent de référence plus récente |
| #22 — TheFab21 | Horaire, coûts, services, données UI et éditeur | Lots 2A, 2B, 3A, 3B ; attribution distincte pour chaque partie effectivement adaptée |
| #24 — TheFab21 | Supplément planning, away/hg et distribution | Lots 2A/3A ; ne pas attribuer deux fois des développements énergie identiques à #22 |

## Matrice de couverture fonctionnelle

| Élément des PRs | Lot / traitement |
|---|---|
| Méthode API de série horaire, chunks et limites de débit | 2B, parseur strict réutilisé |
| Statistiques horaires périodiques et options d’intervalle | 2B, activation explicite, intervalle initial 120 min |
| Historique horaire/quotidien jusqu’à 730 jours | 2B, défaut quotidien conservé, granularity et alias documentés |
| Déduplication, reprise après arrêt et coordination import/updater | 2B, rollback/acquittement et isolation par entrée |
| Cumul historique au lieu de capteur énergie journalier | Valeur ajoutée portée par une nouvelle série stable ; capteur journalier conservé |
| Total domicile cumulatif | 2B : série/cumul horaire distinct avec contrôle des pièces incomplètes ; conserver l’agrégat journalier existant et ses garanties, sans retrait implicite de state_class |
| Capteur et statistiques de coût | 3B, identité séparée et devise validée |
| Tarif fixe, entité HA et prix historique | 3B, convention horaire explicite, pas de prix courant rétroactif silencieux |
| Recalcul des coûts | 3B, service réel testé, ciblage et idempotence |
| Migration des anciens capteurs coût | 3B, inventaire et reprise facultative sans supprimer des entités étrangères |
| Créneaux d’un planning inactif, choix nom/ID | 2A, défaut actif et anciens champs préservés |
| Sauvegarde du timetable complet | 2A, nouveau sync_schedule via le moteur partagé |
| Températures away/hg du planning | 2A, validation et conservation des champs non modifiés |
| Normalisation des transitions et continuité hebdomadaire | 2A, validation/cycle du socle conservés, pas de normalisation arbitraire d’une erreur |
| Noms calendar/device number après renommage | 2A, IDs et noms personnalisés conservés |
| room_names, index/listes de plannings, sept jours | 2A, summaries existants enrichis et héritage des jours affichable |
| Capteur individuel supplémentaire inutilisé | Besoin couvert par summaries existants ; classe morte non reprise |
| Callback climate de fin d’override | Besoin déjà couvert par timers et retrait du socle ; conserver les régressions |
| Modifications du fuseau/cache et snapshots des services | Conserver l’implémentation actuelle ; pas de retour aux anciens handlers |
| Logs supplémentaires radiator_state | 2A : diagnostic utile seulement, sans payload ni console de debug permanents |
| UI grille/semaine, zones, horaires, multi-planning et changements non enregistrés | 3A, adapter l’HTML de TheFab21 |
| Réglages des températures par pièce et away/hg dans l’UI | 3A consommant 2A |
| Connexion iframe et navigateur autonome, reconnexion bornée | 3A, sessions authentifiées et token explicite |
| Thèmes, Firefox, rafraîchissement et messages de sauvegarde | 3A, parcours frontend vérifiés |
| Installation automatique, route HTTP, asset embarqué et ETag | 3A, lifecycle multi-entrée et compatibilité testés |
| README, traductions et exemples | Chaque lot, source et comportement réellement livré |
| Version manifest | Décision au moment de la livraison ; ne pas copier automatiquement 2.0.1 |
| Éléments déjà fusionnés et crédit des propositions antérieures | Lot 1 et contrôle final de chaque lot |

### Points de conception à ne pas perdre

- **Énergie** : ne pas convertir le capteur journalier existant en compteur à vie.
  Les statistiques externes ont une identité home/room stable distincte, avec
  validation précoce de leur usage dans le tableau énergie sur les deux HA.
  Une limite du prototype doit être résolue dans le design avant d’implémenter un
  autre contrat, pas masquée par une modification d’ID.
- **Import** : heures closes depuis au moins 15 minutes, relecture 48 heures et
  rattrapage automatique jusqu’à 7 jours ; historique manuel pour le reste.
  Les corrections tardives du cloud motivent la relecture.
- **Coûts** : la convention de prix historique et de devise est documentée ;
  précision intra-horaire limitée par la résolution énergétique. Les trous ne sont
  pas comblés silencieusement. Un tarif négatif valide ne doit pas être confondu
  avec une énergie négative invalide.
- **Plannings** : le même verrou arbitre services, number, timetable complet et
  températures. L’API ne garantit pas l’atomicité face à une application externe.
- **UI** : aucune donnée/commande non authentifiée, aucun token persistant par
  défaut, noms cloud rendus comme texte. Une sauvegarde composée peut être
  partielle ; l’interface doit le dire.
- **Compatibilité** : IDs, stockage et anciennes automatisations préservés,
  minimum HA 2024.6 et matrice 2024.6.4/2026.10.4 maintenus.

## Crédit à chaque étape

Le [registre CONTRIBUTORS.md](../CONTRIBUTORS.md) reconnaît le créateur et les
auteurs vérifiés : tranb3r, halfred, chrislek, sremy91 et TheFab21.
La reprise horaire, coûts et planning est explicitement attribuée à **TheFab21**.

Pour chaque livraison :

1. Relever PR, commit source, fichiers/idées réellement adaptés et auteur.
2. Conserver l’auteur d’un commit repris tel quel ; sinon utiliser les trailers
   Adapted-from et Original-author et décrire le travail d’adaptation.
3. Conserver les notices originales et le crédit du créateur ; ne pas inventer
   d’adresse de messagerie ou de coauteur.
4. Ajouter le crédit dans la description, les notes de version, le registre et
   les sources concernées. L’aide du planning affiche aussi son auteur source.
5. Si des correctifs du fork adrienvsj sont repris, ajouter leurs propres liens,
   révisions et auteur ; ne pas les attribuer uniquement à la PR d’origine.
6. Passer le statut à livré seulement après implémentation et validation.
   Clôturer, fusionner ou commenter sur GitHub reste une action de livraison
   distincte de la présente planification.

## Critères de sortie par lot

- Scénarios des specs exercés sur le code de production et points d’entrée réels.
- Tests ciblés puis matrice complète HA 2024.6.4/2026.10.4 et Ruff réussis.
- Vrais workers recorder pour heures/coûts, tests de rollback/continuité/unload ;
  aucun compte ni équipement Intuis dans les contrôles automatisés.
- Pour l’UI : logique JS et HTTP, puis parcours iframe/autonome Firefox/Chromium,
  auth, erreurs partielles, cache et reconnexion.
- Identifiants et automatismes historiques inchangés, documentation et crédits à jour.
- Cases cochées seulement après réalisation, résultats et limites consignés.
- Validation OpenSpec stricte ; archivage uniquement après livraison réelle.

## Rollout

Livrer des changements séparés avec leurs crédits et notes de compatibilité,
puis préparer une version de test. L’activation des nouvelles fonctions énergie
et coût est volontaire. Prévoir une vérification manuelle documentée avant
publication, sans présumer qu’elle a eu lieu pendant les tests hors ligne.
Ne pas annoncer de CI distante, de validation cloud ou de publication non effectuée.
Un retour au code précédent ne doit pas effacer les statistiques déjà confirmées.

## Suivi

```sh
openspec list
openspec validate --all --strict
openspec status --change add-hourly-energy-statistics
```

Chaque changement contient proposal.md, design.md, specs/ et tasks.md.
Les cases ouvertes représentent le travail à faire, y compris le contrôle final
de l’attribution ; l’existence de ce document ne vaut pas réalisation de ces lots.

## Validation de la planification

OpenSpec 1.15.0 : les onze changements (six du socle et cinq nouveaux) passent
`validate --all --strict`. Les cinq nouveaux lots contiennent 36 tâches ouvertes.
Les artefacts attendus, la numérotation, les liens locaux Markdown et les espaces
de fin de ligne sont contrôlés. Aucun test produit n’est relancé pour ces seuls
ajouts documentaires ; la référence du socle reste sa validation précédente.
